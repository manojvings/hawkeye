# app/integrations/cortex_client.py
"""Cortex integration client for analyzer and responder execution"""
import asyncio
import aiohttp
import json
import time
from typing import Dict, List, Optional, Any, Union
from uuid import uuid4
from datetime import datetime, timezone
from loguru import logger
from cryptography.fernet import Fernet
import os

from app.db.models.cortex import CortexInstance, CortexAnalyzer, CortexResponder
from app.db.models.enums import JobStatus, WorkerType
from app.core.config import settings


class CortexError(Exception):
    """Cortex integration error"""
    pass


class CortexClient:
    """Async HTTP client for Cortex API interaction"""
    
    def __init__(self, instance: CortexInstance):
        self.instance = instance
        self.base_url = instance.url.rstrip('/')
        self.api_key = self._decrypt_api_key(instance.api_key)
        self.timeout = aiohttp.ClientTimeout(total=instance.timeout)
        self.verify_ssl = instance.verify_ssl
        
    def _decrypt_api_key(self, encrypted_key: str) -> str:
        """Decrypt the stored API key"""
        try:
            # Use environment variable for encryption key
            encryption_key = os.environ.get('CORTEX_ENCRYPTION_KEY')
            if not encryption_key:
                raise ValueError("CORTEX_ENCRYPTION_KEY environment variable not set")
            
            fernet = Fernet(encryption_key.encode())
            return fernet.decrypt(encrypted_key.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt Cortex API key: {e}")
            raise CortexError("Failed to decrypt API key")

    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        files: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make authenticated HTTP request to Cortex"""
        
        url = f"{self.base_url}/api{endpoint}"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json' if not files else None
        }
        
        # Remove Content-Type for file uploads
        if files:
            headers.pop('Content-Type', None)
        
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        
        try:
            async with aiohttp.ClientSession(
                connector=connector, 
                timeout=self.timeout,
                headers={'Authorization': f'Bearer {self.api_key}'}
            ) as session:
                
                kwargs = {
                    'params': params,
                    'ssl': self.verify_ssl
                }
                
                if files:
                    # Handle file uploads
                    form_data = aiohttp.FormData()
                    for key, value in (data or {}).items():
                        form_data.add_field(key, str(value))
                    for key, file_data in files.items():
                        form_data.add_field(key, file_data['content'], filename=file_data['filename'])
                    kwargs['data'] = form_data
                elif data:
                    kwargs['json'] = data
                
                async with session.request(method, url, **kwargs) as response:
                    response_text = await response.text()
                    
                    if response.status >= 400:
                        logger.error(f"Cortex API error {response.status}: {response_text}")
                        raise CortexError(f"HTTP {response.status}: {response_text}")
                    
                    try:
                        return json.loads(response_text) if response_text else {}
                    except json.JSONDecodeError:
                        return {'raw_response': response_text}
        
        except asyncio.TimeoutError:
            raise CortexError(f"Request timeout after {self.timeout}")
        except aiohttp.ClientError as e:
            raise CortexError(f"Connection error: {e}")

    async def get_analyzers(self) -> List[Dict[str, Any]]:
        """Get list of available analyzers"""
        return await self._make_request('GET', '/analyzer')
    
    async def get_analyzer_by_name(self, name: str) -> Dict[str, Any]:
        """Get specific analyzer by name"""
        analyzers = await self.get_analyzers()
        for analyzer in analyzers:
            if analyzer.get('name') == name:
                return analyzer
        raise CortexError(f"Analyzer '{name}' not found")
    
    async def get_analyzers_by_type(self, data_type: str) -> List[Dict[str, Any]]:
        """Get analyzers that support a specific data type"""
        return await self._make_request('GET', f'/analyzer/type/{data_type}')
    
    async def get_responders(self) -> List[Dict[str, Any]]:
        """Get list of available responders"""
        return await self._make_request('GET', '/responder')
    
    async def get_responder_by_name(self, name: str) -> Dict[str, Any]:
        """Get specific responder by name"""
        responders = await self.get_responders()
        for responder in responders:
            if responder.get('name') == name:
                return responder
        raise CortexError(f"Responder '{name}' not found")
    
    async def get_responders_by_type(self, data_type: str) -> List[Dict[str, Any]]:
        """Get responders that support a specific data type"""
        return await self._make_request('GET', f'/responder/type/{data_type}')

    async def run_analyzer(
        self, 
        analyzer_id: str, 
        data: str, 
        data_type: str, 
        tlp: int = 2,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run an analyzer on data"""
        
        job_data = {
            'dataType': data_type,
            'data': data,
            'tlp': tlp,
            'parameters': parameters or {}
        }
        
        response = await self._make_request('POST', f'/analyzer/{analyzer_id}/run', data=job_data)
        return response
    
    async def run_analyzer_on_file(
        self, 
        analyzer_id: str, 
        file_content: bytes, 
        filename: str,
        tlp: int = 2,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run an analyzer on a file"""
        
        job_data = {
            'dataType': 'file',
            'tlp': tlp,
            'parameters': json.dumps(parameters or {})
        }
        
        files = {
            'attachment': {
                'content': file_content,
                'filename': filename
            }
        }
        
        response = await self._make_request('POST', f'/analyzer/{analyzer_id}/run', data=job_data, files=files)
        return response

    async def run_responder(
        self,
        responder_id: str,
        object_type: str,
        object_id: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run a responder on an object"""
        
        job_data = {
            'objectType': object_type,
            'objectId': object_id,
            'parameters': parameters or {}
        }
        
        response = await self._make_request('POST', f'/responder/{responder_id}/run', data=job_data)
        return response

    async def get_job(self, job_id: str) -> Dict[str, Any]:
        """Get job details and status"""
        return await self._make_request('GET', f'/job/{job_id}')
    
    async def wait_for_job(self, job_id: str, max_wait: int = 300, poll_interval: int = 5) -> Dict[str, Any]:
        """Wait for job completion with polling"""
        
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            job = await self.get_job(job_id)
            status = job.get('status')
            
            if status in ['Success', 'Failure']:
                return job
            
            await asyncio.sleep(poll_interval)
        
        raise CortexError(f"Job {job_id} did not complete within {max_wait} seconds")
    
    async def get_job_report(self, job_id: str) -> Dict[str, Any]:
        """Get job execution report"""
        return await self._make_request('GET', f'/job/{job_id}/report')
    
    async def get_job_artifacts(self, job_id: str) -> List[Dict[str, Any]]:
        """Get artifacts generated by job"""
        return await self._make_request('GET', f'/job/{job_id}/artifacts')
    
    async def delete_job(self, job_id: str) -> bool:
        """Delete a job"""
        try:
            await self._make_request('DELETE', f'/job/{job_id}')
            return True
        except CortexError:
            return False

    async def health_check(self) -> Dict[str, Any]:
        """Check Cortex instance health"""
        try:
            response = await self._make_request('GET', '/status')
            return {
                'status': 'healthy',
                'version': response.get('version'),
                'response_time': time.time()
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'response_time': time.time()
            }


class CortexManager:
    """High-level Cortex integration manager"""
    
    def __init__(self):
        self.clients: Dict[str, CortexClient] = {}
    
    def add_instance(self, instance: CortexInstance) -> None:
        """Add Cortex instance"""
        self.clients[instance.name] = CortexClient(instance)
    
    def remove_instance(self, instance_name: str) -> None:
        """Remove Cortex instance"""
        self.clients.pop(instance_name, None)
    
    def get_client(self, instance_name: str) -> Optional[CortexClient]:
        """Get client for specific instance"""
        return self.clients.get(instance_name)
    
    async def sync_workers(self, instance: CortexInstance) -> Dict[str, int]:
        """Sync analyzers and responders from Cortex instance"""
        client = self.get_client(instance.name)
        if not client:
            raise CortexError(f"Client for instance '{instance.name}' not found")
        
        stats = {'analyzers': 0, 'responders': 0, 'errors': 0}
        
        try:
            # Sync analyzers
            analyzers_data = await client.get_analyzers()
            for analyzer_data in analyzers_data:
                try:
                    await self._sync_analyzer(instance, analyzer_data)
                    stats['analyzers'] += 1
                except Exception as e:
                    logger.error(f"Failed to sync analyzer {analyzer_data.get('name')}: {e}")
                    stats['errors'] += 1
            
            # Sync responders
            responders_data = await client.get_responders()
            for responder_data in responders_data:
                try:
                    await self._sync_responder(instance, responder_data)
                    stats['responders'] += 1
                except Exception as e:
                    logger.error(f"Failed to sync responder {responder_data.get('name')}: {e}")
                    stats['errors'] += 1
        
        except Exception as e:
            logger.error(f"Failed to sync workers for instance {instance.name}: {e}")
            raise CortexError(f"Sync failed: {e}")
        
        return stats
    
    async def _sync_analyzer(self, instance: CortexInstance, data: Dict[str, Any]) -> None:
        """Sync individual analyzer (this would be implemented with database access)"""
        # This is a placeholder - would need database session to implement
        logger.info(f"Syncing analyzer: {data.get('name')} v{data.get('version')}")
    
    async def _sync_responder(self, instance: CortexInstance, data: Dict[str, Any]) -> None:
        """Sync individual responder (this would be implemented with database access)"""
        # This is a placeholder - would need database session to implement
        logger.info(f"Syncing responder: {data.get('name')} v{data.get('version')}")
    
    async def run_analysis(
        self,
        instance_name: str,
        analyzer_name: str,
        observable_data: str,
        observable_type: str,
        tlp: int = 2,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run analysis on observable data"""
        
        client = self.get_client(instance_name)
        if not client:
            raise CortexError(f"Client for instance '{instance_name}' not found")
        
        # Get analyzer details
        analyzer = await client.get_analyzer_by_name(analyzer_name)
        analyzer_id = analyzer.get('id')
        
        if not analyzer_id:
            raise CortexError(f"Analyzer '{analyzer_name}' not found")
        
        # Run analysis
        job = await client.run_analyzer(
            analyzer_id=analyzer_id,
            data=observable_data,
            data_type=observable_type,
            tlp=tlp,
            parameters=parameters
        )
        
        return job
    
    async def run_response(
        self,
        instance_name: str,
        responder_name: str,
        object_type: str,
        object_id: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run responder on object"""
        
        client = self.get_client(instance_name)
        if not client:
            raise CortexError(f"Client for instance '{instance_name}' not found")
        
        # Get responder details
        responder = await client.get_responder_by_name(responder_name)
        responder_id = responder.get('id')
        
        if not responder_id:
            raise CortexError(f"Responder '{responder_name}' not found")
        
        # Run responder
        job = await client.run_responder(
            responder_id=responder_id,
            object_type=object_type,
            object_id=object_id,
            parameters=parameters
        )
        
        return job


# Global instance
cortex_manager = CortexManager()