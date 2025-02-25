import os
import tensorflow as tf
from typing import List, Optional, Union
import logging
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pathlib import Path
import contextlib
import tempfile
import shutil

logger = logging.getLogger(__name__)

class TensorFlowIOInterceptor:
    """Interceptor for TensorFlow I/O operations to control where models can be saved and how."""
    
    def __init__(
        self,
        whitelist_paths: Optional[List[str]] = None,
        non_whitelist_action: str = "encrypt",
        salt: Optional[bytes] = None
    ):
        """Initialize the TensorFlowIOInterceptor.
        
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
            self.salt = salt if salt else os.urandom(16)
        
        # Store original functions
        self.original_functions = {
            'model.save': tf.keras.Model.save,
            'model.save_weights': tf.keras.Model.save_weights,
            'saved_model.save': tf.saved_model.save
        }
        self._is_active = False
        
        # Add distributed strategy detection
        self.strategy = tf.distribute.get_strategy()
        self.is_distributed = isinstance(self.strategy, (
            tf.distribute.MirroredStrategy,
            tf.distribute.MultiWorkerMirroredStrategy,
            tf.distribute.experimental.ParameterServerStrategy
        ))
        if self.is_distributed:
            # In TF, we can use replica_id to identify the main worker
            self.is_main_worker = (self.strategy.cluster_resolver.task_id == 0)
        else:
            self.is_main_worker = True
    
    @contextlib.contextmanager
    def activate(self):
        """Context manager to safely patch and restore save functions."""
        try:
            # Patch functions
            tf.keras.Model.save = self._intercepted_save
            tf.keras.Model.save_weights = self._intercepted_save_weights
            tf.saved_model.save = self._intercepted_saved_model_save
            self._is_active = True
            
            yield self
        finally:
            # Always restore original functions, even if an error occurs
            self.restore()
    
    def _is_path_whitelisted(self, filepath: Union[str, Path]) -> bool:
        """Check if the given path is in the whitelist."""
        abs_path = os.path.abspath(filepath)
        return any(abs_path.startswith(wp) for wp in self.whitelist_paths)
    
    def _hash_directory(self, directory: str) -> bytes:
        """Create a hash of an entire directory."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        
        # Create a temporary directory to save the model
        with tempfile.TemporaryDirectory() as temp_dir:
            # Copy directory contents to temp dir
            if os.path.exists(directory):
                shutil.copytree(directory, temp_dir, dirs_exist_ok=True)
            
            # Concatenate all files' contents in a deterministic order
            all_contents = b""
            for root, _, files in sorted(os.walk(temp_dir)):
                for file in sorted(files):
                    file_path = os.path.join(root, file)
                    with open(file_path, 'rb') as f:
                        all_contents += f.read()
        
        return kdf.derive(all_contents)
    
    def _save_hash(self, hash_data: bytes, filepath: str):
        """Save hash data with salt."""
        hash_filepath = filepath + ".hash"
        with open(hash_filepath, "wb") as f:
            f.write(self.salt)
            f.write(hash_data)
        logger.info(f"Model saved with one-way hash at: {hash_filepath}")
    
    def _intercepted_save(self, filepath, *args, **kwargs):
        """Intercepted version of model.save."""
        if not self._is_active:
            raise RuntimeError("TensorFlowIOInterceptor must be used within 'activate' context")
        
        try:
            # Only main worker should handle saving
            if not self.is_main_worker:
                return
            
            if self._is_path_whitelisted(filepath):
                return self.original_functions['model.save'](self, filepath, *args, **kwargs)
            
            if self.non_whitelist_action == "ignore":
                logger.warning(f"Write operation ignored for non-whitelisted path: {filepath}")
                return
            
            elif self.non_whitelist_action == "encrypt":
                # Save to temporary directory first
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = os.path.join(temp_dir, "model")
                    self.original_functions['model.save'](self, temp_path, *args, **kwargs)
                    hash_data = self._hash_directory(temp_path)
                    self._save_hash(hash_data, filepath)
        except Exception as e:
            logger.error(f"Error during intercepted save: {str(e)}")
            raise
    
    def _intercepted_save_weights(self, filepath, *args, **kwargs):
        """Intercepted version of model.save_weights."""
        if not self._is_active:
            raise RuntimeError("TensorFlowIOInterceptor must be used within 'activate' context")
        
        try:
            # Only main worker should handle saving
            if not self.is_main_worker:
                return
            
            if self._is_path_whitelisted(filepath):
                return self.original_functions['model.save_weights'](self, filepath, *args, **kwargs)
            
            if self.non_whitelist_action == "ignore":
                logger.warning(f"Write operation ignored for non-whitelisted path: {filepath}")
                return
            
            elif self.non_whitelist_action == "encrypt":
                # Save to temporary file first
                with tempfile.NamedTemporaryFile() as temp_file:
                    self.original_functions['model.save_weights'](self, temp_file.name, *args, **kwargs)
                    with open(temp_file.name, 'rb') as f:
                        data = f.read()
                    
                    kdf = PBKDF2HMAC(
                        algorithm=hashes.SHA256(),
                        length=32,
                        salt=self.salt,
                        iterations=100000,
                    )
                    hash_data = kdf.derive(data)
                    self._save_hash(hash_data, filepath)
        except Exception as e:
            logger.error(f"Error during intercepted save: {str(e)}")
            raise
    
    def _intercepted_saved_model_save(self, model, filepath, *args, **kwargs):
        """Intercepted version of tf.saved_model.save."""
        if not self._is_active:
            raise RuntimeError("TensorFlowIOInterceptor must be used within 'activate' context")
        
        try:
            # Only main worker should handle saving
            if not self.is_main_worker:
                return
            
            if self._is_path_whitelisted(filepath):
                return self.original_functions['saved_model.save'](model, filepath, *args, **kwargs)
            
            if self.non_whitelist_action == "ignore":
                logger.warning(f"Write operation ignored for non-whitelisted path: {filepath}")
                return
            
            elif self.non_whitelist_action == "encrypt":
                # Save to temporary directory first
                with tempfile.TemporaryDirectory() as temp_dir:
                    self.original_functions['saved_model.save'](model, temp_dir, *args, **kwargs)
                    hash_data = self._hash_directory(temp_dir)
                    self._save_hash(hash_data, filepath)
        except Exception as e:
            logger.error(f"Error during intercepted save: {str(e)}")
            raise
    
    def restore(self):
        """Restore all original functions."""
        if self._is_active:
            tf.keras.Model.save = self.original_functions['model.save']
            tf.keras.Model.save_weights = self.original_functions['model.save_weights']
            tf.saved_model.save = self.original_functions['saved_model.save']
            self._is_active = False
    
    def verify_hash(self, model_or_weights, hashed_filepath: str, save_format: str = 'tf') -> bool:
        """Verify if a model matches a previously saved hash.
        
        Args:
            model_or_weights: The model or weights to verify
            hashed_filepath: Path to the hashed file (.hash)
            save_format: Format used for saving ('tf' or 'keras' or 'weights')
        
        Returns:
            bool: True if the model matches the hash
        """
        if not hashed_filepath.endswith('.hash'):
            raise ValueError("Hashed file must have .hash extension")
        
        # Read the saved hash and salt
        with open(hashed_filepath, 'rb') as f:
            saved_salt = f.read(16)
            saved_hash = f.read()
        
        # Create hash of the current model
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = os.path.join(temp_dir, "model")
            
            # Save based on format
            if save_format == 'weights':
                model_or_weights.save_weights(temp_path)
                with open(temp_path, 'rb') as f:
                    data = f.read()
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=saved_salt,
                    iterations=100000,
                )
                new_hash = kdf.derive(data)
            else:
                if save_format == 'tf':
                    tf.saved_model.save(model_or_weights, temp_path)
                else:  # keras format
                    model_or_weights.save(temp_path)
                
                # Hash the entire directory
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=saved_salt,
                    iterations=100000,
                )
                all_contents = b""
                for root, _, files in sorted(os.walk(temp_path)):
                    for file in sorted(files):
                        file_path = os.path.join(root, file)
                        with open(file_path, 'rb') as f:
                            all_contents += f.read()
                new_hash = kdf.derive(all_contents)
        
        return saved_hash == new_hash 