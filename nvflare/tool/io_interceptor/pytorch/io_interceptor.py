# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import torch
from typing import List, Optional, Union
import logging
from cryptography.fernet import Fernet
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
import pickle
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import contextlib

logger = logging.getLogger(__name__)

class TorchIOInterceptor:
    """Interceptor for PyTorch I/O operations to control where models can be saved and how."""
    
    def __init__(
        self,
        whitelist_paths: Optional[List[str]] = None,
        non_whitelist_action: str = "encrypt",
        salt: Optional[bytes] = None  # Optional fixed salt
    ):
        """Initialize the TorchIOInterceptor.
        
        Args:
            whitelist_paths: List of paths where saving is allowed without encryption
            non_whitelist_action: Action to take for non-whitelisted paths ("encrypt" or "ignore")
            salt: Optional fixed salt for one-way encryption
        """
        self.whitelist_paths = [os.path.abspath(p) for p in (whitelist_paths or [])]
        if non_whitelist_action not in ["encrypt", "ignore"]:
            raise ValueError("non_whitelist_action must be either 'encrypt' or 'ignore'")
        self.non_whitelist_action = non_whitelist_action
        
        if non_whitelist_action == "encrypt":
            # Generate or use provided salt
            self.salt = salt if salt else os.urandom(16)
        
        # Don't patch in __init__, wait for context manager
        self.original_functions = {
            'torch.save': torch.save,
            'torch.jit.save': torch.jit.save,
            'torch.nn.Module.save_state_dict': torch.nn.Module.save_state_dict,
            'pickle.dump': pickle.dump
        }
        self._is_active = False
        
        self.is_distributed = torch.distributed.is_initialized()
        if self.is_distributed:
            self.rank = torch.distributed.get_rank()
        else:
            self.rank = 0
    
    @contextlib.contextmanager
    def activate(self):
        """Context manager to safely patch and restore save functions."""
        try:
            # Patch functions
            torch.save = self._intercepted_save
            torch.jit.save = self._intercepted_jit_save
            torch.nn.Module.save_state_dict = self._intercepted_state_dict_save
            pickle.dump = self._intercepted_pickle_dump
            self._is_active = True
            
            yield self
        finally:
            # Always restore original functions, even if an error occurs
            self.restore()
    
    def _is_path_whitelisted(self, filepath: Union[str, Path]) -> bool:
        """Check if the given path is in the whitelist."""
        abs_path = os.path.abspath(filepath)
        return any(abs_path.startswith(wp) for wp in self.whitelist_paths)
    
    def _intercepted_save(self, obj, filepath, *args, **kwargs):
        """Intercepted version of torch.save that implements our security policies."""
        if not self._is_active:
            raise RuntimeError("TorchIOInterceptor must be used within 'activate' context")
            
        try:
            if self.is_distributed and self.rank != 0:
                return
            
            if self._is_path_whitelisted(filepath):
                return self.original_functions['torch.save'](obj, filepath, *args, **kwargs)
            
            if self.non_whitelist_action == "ignore":
                logger.warning(f"Write operation ignored for non-whitelisted path: {filepath}")
                return
            
            elif self.non_whitelist_action == "encrypt":
                # Save to buffer first
                buffer = torch.ByteStorage()
                self.original_functions['torch.save'](obj, buffer, *args, **kwargs)
                data = bytes(buffer)
                
                # Create one-way hash of the data
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=self.salt,
                    iterations=100000,
                )
                hashed_data = kdf.derive(data)
                
                # Write hashed data
                enc_filepath = str(filepath) + ".hash"
                with open(enc_filepath, "wb") as f:
                    f.write(self.salt)
                    f.write(hashed_data)
                
                logger.info(f"Model saved with one-way hash at: {enc_filepath}")
        except Exception as e:
            logger.error(f"Error during intercepted save: {str(e)}")
            raise
    
    def restore(self):
        """Restore all original functions."""
        if self._is_active:
            for name, func in self.original_functions.items():
                if name == 'torch.save':
                    torch.save = func
                elif name == 'torch.jit.save':
                    torch.jit.save = func
                elif name == 'torch.nn.Module.save_state_dict':
                    torch.nn.Module.save_state_dict = func
                elif name == 'pickle.dump':
                    pickle.dump = func
            self._is_active = False

    def verify_hash(self, original_model, hashed_filepath: str) -> bool:
        """Verify if a model matches a previously saved hash.
        
        Args:
            original_model: The model to verify
            hashed_filepath: Path to the hashed file (.hash)
        
        Returns:
            bool: True if the model matches the hash
        """
        if not hashed_filepath.endswith('.hash'):
            raise ValueError("Hashed file must have .hash extension")
        
        # Read the saved hash and salt
        with open(hashed_filepath, 'rb') as f:
            saved_salt = f.read(16)  # First 16 bytes are salt
            saved_hash = f.read()    # Rest is the hash
        
        # Create hash of the original model
        buffer = torch.ByteStorage()
        self.original_functions['torch.save'](original_model, buffer)
        data = bytes(buffer)
        
        # Create hash with the same salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=saved_salt,
            iterations=100000,
        )
        new_hash = kdf.derive(data)
        
        # Compare hashes
        return saved_hash == new_hash