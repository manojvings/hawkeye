# app/integrations/webhook_manager.py
"""Webhook management and delivery system"""
import asyncio
import aiohttp
import json
import hmac
import hashlib
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone, timedelta
from loguru import logger
from jinja2 import Template, Environment, select_autoescape
import backoff

from app.db.models.webhook import Webhook, WebhookDelivery, WebhookTemplate
from app.db.models.enums import WebhookEvent, WebhookStatus
from app.core.config import settings


class WebhookError(Exception):
    """Webhook processing error"""
    pass


class WebhookManager:
    """Manages webhook delivery and processing"""
    
    def __init__(self):
        self.jinja_env = Environment(
            autoescape=select_autoescape(['html', 'xml']),
            enable_async=True
        )
        self.delivery_queue = asyncio.Queue()
        self.retry_queue = asyncio.Queue()
        self.running = False
        self.workers = []

    async def start(self, num_workers: int = 3):
        """Start webhook delivery workers"""
        if self.running:
            return
        
        self.running = True
        
        # Start delivery workers
        for i in range(num_workers):
            worker = asyncio.create_task(self._delivery_worker(f"worker-{i}"))
            self.workers.append(worker)
        
        # Start retry worker
        retry_worker = asyncio.create_task(self._retry_worker())
        self.workers.append(retry_worker)
        
        logger.info(f"Webhook manager started with {num_workers} workers")

    async def stop(self):
        """Stop webhook delivery workers"""
        self.running = False
        
        # Cancel all workers
        for worker in self.workers:
            worker.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        
        logger.info("Webhook manager stopped")

    async def trigger_event(
        self,
        event_type: WebhookEvent,
        event_data: Dict[str, Any],
        webhooks: List[Webhook],
        triggered_by_id: Optional[int] = None,
        related_objects: Optional[Dict[str, int]] = None
    ):
        """Trigger webhook event for matching webhooks"""
        
        for webhook in webhooks:
            # Check if webhook listens to this event
            if event_type.value not in webhook.events:
                continue
            
            # Check if webhook is enabled
            if not webhook.enabled:
                continue
            
            # Apply filters (organization, case criteria, etc.)
            if not self._matches_filters(webhook, event_data):
                continue
            
            try:
                # Create delivery record
                delivery = await self._create_delivery(
                    webhook=webhook,
                    event_type=event_type,
                    event_data=event_data,
                    triggered_by_id=triggered_by_id,
                    related_objects=related_objects or {}
                )
                
                # Queue for delivery
                await self.delivery_queue.put(delivery)
                
                logger.debug(f"Queued webhook delivery: {delivery.uuid}")
                
            except Exception as e:
                logger.error(f"Failed to create webhook delivery for {webhook.name}: {e}")

    def _matches_filters(self, webhook: Webhook, event_data: Dict[str, Any]) -> bool:
        """Check if event matches webhook filters"""
        
        # Organization filter
        if webhook.organization_filter:
            org_id = event_data.get('organization', {}).get('id')
            if org_id not in webhook.organization_filter:
                return False
        
        # Case filter (if event is case-related)
        if webhook.case_filter and 'case' in event_data:
            case_data = event_data['case']
            
            # Status filter
            if 'status' in webhook.case_filter:
                if case_data.get('status') not in webhook.case_filter['status']:
                    return False
            
            # Severity filter
            if 'severity' in webhook.case_filter:
                if case_data.get('severity') not in webhook.case_filter['severity']:
                    return False
            
            # Tag filter
            if 'tags' in webhook.case_filter:
                case_tags = set(case_data.get('tags', []))
                required_tags = set(webhook.case_filter['tags'])
                if not required_tags.intersection(case_tags):
                    return False
        
        return True

    async def _create_delivery(
        self,
        webhook: Webhook,
        event_type: WebhookEvent,
        event_data: Dict[str, Any],
        triggered_by_id: Optional[int] = None,
        related_objects: Dict[str, int] = None
    ) -> WebhookDelivery:
        """Create webhook delivery record"""
        
        # This would need database session - simplified for now
        delivery_data = {
            'webhook_id': webhook.id,
            'event_type': event_type,
            'status': WebhookStatus.PENDING,
            'request_url': webhook.url,
            'request_method': 'POST',
            'request_headers': self._build_headers(webhook, event_data),
            'request_body': await self._build_payload(webhook, event_type, event_data),
            'event_data': event_data,
            'triggered_by_id': triggered_by_id,
            'max_attempts': webhook.max_retries + 1,
            **related_objects
        }
        
        # In a real implementation, this would create and return a WebhookDelivery object
        logger.info(f"Created delivery for webhook {webhook.name}")
        return delivery_data

    def _build_headers(self, webhook: Webhook, event_data: Dict[str, Any]) -> Dict[str, str]:
        """Build HTTP headers for webhook request"""
        
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': f'CHawk-Webhook/1.0',
            'X-CHawk-Event': event_data.get('event_type', ''),
            'X-CHawk-Delivery': str(time.time()),
        }
        
        # Add custom headers
        headers.update(webhook.custom_headers)
        
        # Add signature if secret is configured
        if webhook.secret:
            payload = json.dumps(event_data, sort_keys=True)
            signature = self._generate_signature(webhook.secret, payload)
            headers['X-CHawk-Signature'] = signature
        
        return headers

    async def _build_payload(
        self,
        webhook: Webhook,
        event_type: WebhookEvent,
        event_data: Dict[str, Any]
    ) -> str:
        """Build webhook payload"""
        
        # Default payload structure
        payload = {
            'event': event_type.value,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'webhook': {
                'id': str(webhook.uuid),
                'name': webhook.name
            },
            'data': event_data
        }
        
        return json.dumps(payload, indent=2)

    def _generate_signature(self, secret: str, payload: str) -> str:
        """Generate HMAC signature for webhook payload"""
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f'sha256={signature}'

    async def _delivery_worker(self, worker_name: str):
        """Worker process for delivering webhooks"""
        logger.info(f"Webhook delivery worker {worker_name} started")
        
        while self.running:
            try:
                # Get delivery from queue (with timeout)
                delivery = await asyncio.wait_for(
                    self.delivery_queue.get(),
                    timeout=1.0
                )
                
                await self._deliver_webhook(delivery)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Webhook worker {worker_name} error: {e}")
        
        logger.info(f"Webhook delivery worker {worker_name} stopped")

    async def _deliver_webhook(self, delivery):
        """Deliver individual webhook"""
        logger.info(f"Delivering webhook to {delivery['request_url']}")
        
        start_time = time.time()
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)  # Default timeout
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method=delivery['request_method'],
                    url=delivery['request_url'],
                    headers=delivery['request_headers'],
                    data=delivery['request_body'],
                    ssl=True  # This should be configurable based on webhook settings
                ) as response:
                    
                    response_time = int((time.time() - start_time) * 1000)
                    response_body = await response.text()
                    
                    # Update delivery record
                    await self._update_delivery_success(
                        delivery,
                        response.status,
                        dict(response.headers),
                        response_body,
                        response_time
                    )
                    
                    logger.info(f"Webhook delivered successfully: {response.status}")
        
        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            
            await self._update_delivery_failure(
                delivery,
                str(e),
                response_time
            )
            
            logger.error(f"Webhook delivery failed: {e}")

    async def _update_delivery_success(
        self,
        delivery,
        status_code: int,
        headers: Dict[str, str],
        body: str,
        response_time: int
    ):
        """Update delivery record on success"""
        # In real implementation, this would update the database record
        logger.info(f"Webhook delivery succeeded: {status_code} in {response_time}ms")

    async def _update_delivery_failure(
        self,
        delivery,
        error_message: str,
        response_time: int
    ):
        """Update delivery record on failure and handle retries"""
        
        delivery['attempt_count'] += 1
        delivery['error_message'] = error_message
        delivery['response_time'] = response_time
        
        # Check if we should retry
        if delivery['attempt_count'] < delivery['max_attempts']:
            # Calculate retry delay with exponential backoff
            delay = min(60 * (2 ** (delivery['attempt_count'] - 1)), 3600)  # Max 1 hour
            retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            
            delivery['next_retry_at'] = retry_at
            delivery['status'] = WebhookStatus.RETRYING
            
            # Queue for retry
            await self.retry_queue.put(delivery)
            
            logger.info(f"Webhook delivery scheduled for retry in {delay}s")
        else:
            delivery['status'] = WebhookStatus.ABANDONED
            logger.error(f"Webhook delivery abandoned after {delivery['attempt_count']} attempts")

    async def _retry_worker(self):
        """Worker process for handling webhook retries"""
        logger.info("Webhook retry worker started")
        
        while self.running:
            try:
                # Check for deliveries ready to retry
                await asyncio.sleep(10)  # Check every 10 seconds
                
                # In real implementation, this would query database for retries due
                # For now, just process retry queue
                while not self.retry_queue.empty():
                    try:
                        delivery = self.retry_queue.get_nowait()
                        
                        # Check if it's time to retry
                        if delivery.get('next_retry_at') and \
                           datetime.now(timezone.utc) >= delivery['next_retry_at']:
                            
                            delivery['status'] = WebhookStatus.PENDING
                            await self.delivery_queue.put(delivery)
                            
                            logger.info(f"Queued webhook delivery for retry")
                        else:
                            # Put back in retry queue
                            await self.retry_queue.put(delivery)
                    
                    except asyncio.QueueEmpty:
                        break
            
            except Exception as e:
                logger.error(f"Webhook retry worker error: {e}")
        
        logger.info("Webhook retry worker stopped")

    # Template rendering methods

    async def render_template(
        self,
        template: WebhookTemplate,
        event_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Render webhook template with event data"""
        
        context = {
            'event': event_data,
            'config': config,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # Render URL
            url_template = self.jinja_env.from_string(template.url_template)
            url = await url_template.render_async(**context)
            
            # Render headers
            rendered_headers = {}
            for key, value_template in template.headers_template.items():
                value_tmpl = self.jinja_env.from_string(str(value_template))
                rendered_headers[key] = await value_tmpl.render_async(**context)
            
            # Render body
            body_template = self.jinja_env.from_string(template.body_template)
            body = await body_template.render_async(**context)
            
            return {
                'url': url,
                'method': template.method,
                'headers': rendered_headers,
                'body': body
            }
        
        except Exception as e:
            logger.error(f"Failed to render webhook template: {e}")
            raise WebhookError(f"Template rendering failed: {e}")

    # Event convenience methods

    async def trigger_case_created(self, case_data: Dict[str, Any], webhooks: List[Webhook], user_id: int):
        """Trigger case created event"""
        await self.trigger_event(
            event_type=WebhookEvent.CASE_CREATED,
            event_data=case_data,
            webhooks=webhooks,
            triggered_by_id=user_id,
            related_objects={'case_id': case_data.get('id')}
        )

    async def trigger_case_updated(self, case_data: Dict[str, Any], webhooks: List[Webhook], user_id: int):
        """Trigger case updated event"""
        await self.trigger_event(
            event_type=WebhookEvent.CASE_UPDATED,
            event_data=case_data,
            webhooks=webhooks,
            triggered_by_id=user_id,
            related_objects={'case_id': case_data.get('id')}
        )

    async def trigger_task_completed(self, task_data: Dict[str, Any], webhooks: List[Webhook], user_id: int):
        """Trigger task completed event"""
        await self.trigger_event(
            event_type=WebhookEvent.TASK_COMPLETED,
            event_data=task_data,
            webhooks=webhooks,
            triggered_by_id=user_id,
            related_objects={'task_id': task_data.get('id')}
        )

    async def trigger_cortex_job_completed(self, job_data: Dict[str, Any], webhooks: List[Webhook]):
        """Trigger Cortex job completed event"""
        await self.trigger_event(
            event_type=WebhookEvent.CORTEX_JOB_COMPLETED,
            event_data=job_data,
            webhooks=webhooks,
            related_objects={'case_id': job_data.get('case_id')}
        )


# Global webhook manager instance
webhook_manager = WebhookManager()