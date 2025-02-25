import os
import mmap
import builtins
import io
from typing import List, Optional, Union
import logging
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pathlib import Path
import contextlib
import tempfile
import shutil
from cryptography.fernet import Fernet
import secrets

logger = logging.getLogger(__name__)

class PythonIOInterceptor:
    """Interceptor for Python I/O operations to control where files can be written."""
    
    def __init__(
        self,
        whitelist_paths: Optional[List[str]] = None,
        non_whitelist_action: str = "encrypt",
        salt: Optional[bytes] = None,
        memory_threshold: int = 400 * 1024 * 1024  # 400MB default
    ):
        """Initialize the PythonIOInterceptor.
        
        Args:
            whitelist_paths: List of paths where writing is allowed without encryption
            non_whitelist_action: Action to take for non-whitelisted paths ("encrypt" or "ignore")
            salt: Optional fixed salt for one-way encryption
            memory_threshold: Size in bytes before switching to temp file (default 400MB)
        """
        self.whitelist_paths = [os.path.abspath(p) for p in (whitelist_paths or [])]
        if non_whitelist_action not in ["encrypt", "ignore"]:
            raise ValueError("non_whitelist_action must be either 'encrypt' or 'ignore'")
        self.non_whitelist_action = non_whitelist_action
        self.memory_threshold = memory_threshold
        
        if non_whitelist_action == "encrypt":
            self.salt = salt if salt else os.urandom(16)
            # Create one cipher for the entire session
            self._temp_key = Fernet.generate_key()
            self._cipher = Fernet(self._temp_key)
        
        self.original_open = builtins.open
        self.original_os_open = os.open
        self.original_os_write = os.write
        self.original_mmap = mmap.mmap
        self._is_active = False
        self._active_files = set()
        self._active_fds = set()  # Track file descriptors
    
    def _is_path_whitelisted(self, filepath: Union[str, Path]) -> bool:
        """Check if the given path is in the whitelist."""
        abs_path = os.path.abspath(filepath)
        return any(abs_path.startswith(wp) for wp in self.whitelist_paths)
    
    def _hash_data(self, data: bytes) -> bytes:
        """Create a hash of the data."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        return kdf.derive(data)
    
    class InterceptedFile:
        """Wrapper for file objects that intercepts write operations."""
        
        def __init__(self, file_obj, filepath: str, interceptor):
            self._file = file_obj
            self._filepath = filepath
            self._interceptor = interceptor
            self._mode = file_obj.mode
            self._closed = False
            self._size = 0
            
            # Start with memory buffer
            self._buffer = io.BytesIO()
            self._using_temp_file = False
            self._temp_path = None
        
        def write(self, data):
            """Write data, switching to temp file if size exceeds threshold."""
            if isinstance(data, str):
                data = data.encode()
            
            data_len = len(data)
            self._size += data_len

            if not self._using_temp_file:
                if self._size <= self._interceptor.memory_threshold:
                    # Keep using memory buffer
                    self._buffer.write(data)
                    return
                
                # Switch to temp file if size exceeds threshold
                temp_dir = tempfile.gettempdir()
                random_name = secrets.token_hex(16)
                self._temp_path = os.path.join(temp_dir, random_name)
                self._using_temp_file = True
                
                # Write buffer contents to temp file
                if self._interceptor.non_whitelist_action == "encrypt" and not self._interceptor._is_path_whitelisted(self._filepath):
                    encrypted_data = self._interceptor._cipher.encrypt(self._buffer.getvalue())
                    with open(self._temp_path, 'wb') as f:
                        f.write(encrypted_data)
                else:
                    with open(self._temp_path, 'wb') as f:
                        f.write(self._buffer.getvalue())
                
                # Clear memory buffer
                self._buffer = None

            # Write to temp file
            if self._interceptor.non_whitelist_action == "encrypt" and not self._interceptor._is_path_whitelisted(self._filepath):
                encrypted_data = self._interceptor._cipher.encrypt(data)
                with open(self._temp_path, 'ab') as f:
                    f.write(encrypted_data)
            else:
                with open(self._temp_path, 'ab') as f:
                    f.write(data)
        
        def close(self):
            """Handle file closing and cleanup."""
            if self._closed:
                return
            
            try:
                if 'w' not in self._mode and 'a' not in self._mode:
                    self._file.close()
                    return
                
                if self._interceptor._is_path_whitelisted(self._filepath):
                    if self._using_temp_file:
                        # Copy temp file to final destination
                        with open(self._temp_path, 'rb') as temp:
                            shutil.copyfileobj(temp, self._file)
                    else:
                        # Write memory buffer directly
                        self._file.write(self._buffer.getvalue())
                    self._file.close()
                
                elif self._interceptor.non_whitelist_action == "ignore":
                    logger.warning(f"Write operation ignored for non-whitelisted path: {self._filepath}")
                    self._file.close()
                
                elif self._interceptor.non_whitelist_action == "encrypt":
                    # Create hash from either temp file or memory buffer
                    kdf = PBKDF2HMAC(
                        algorithm=hashes.SHA256(),
                        length=32,
                        salt=self._interceptor.salt,
                        iterations=100000,
                    )
                    
                    if self._using_temp_file:
                        with open(self._temp_path, 'rb') as temp:
                            while True:
                                chunk = temp.read(8192)
                                if not chunk:
                                    break
                                if not self._interceptor._is_path_whitelisted(self._filepath):
                                    chunk = self._interceptor._cipher.decrypt(chunk)
                                kdf.update(chunk)
                    else:
                        kdf.update(self._buffer.getvalue())
                    
                    hashed_data = kdf.finalize()
                    self._file.close()
                    
                    # Write hash
                    hash_filepath = self._filepath + ".hash"
                    with open(hash_filepath, "wb") as f:
                        f.write(self._interceptor.salt)
                        f.write(hashed_data)
            
            finally:
                self._closed = True
                self._interceptor._active_files.remove(self)
                
                # Clean up resources
                if self._using_temp_file:
                    self._secure_delete(self._temp_path)
                if self._buffer:
                    self._buffer = None
        
        def _secure_delete(self, path):
            """Securely delete a file by overwriting with random data."""
            if os.path.exists(path):
                size = os.path.getsize(path)
                with open(path, 'wb') as f:
                    # Overwrite with random data
                    f.write(os.urandom(size))
                    f.flush()
                    os.fsync(f.fileno())
                os.unlink(path)
        
        def __getattr__(self, name):
            """Delegate all other attributes to the underlying file object."""
            return getattr(self._file, name)
        
        def __enter__(self):
            """Context manager entry."""
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            """Context manager exit."""
            self.close()
    
    def _intercepted_open(self, file, mode='r', *args, **kwargs):
        """Intercepted version of built-in open."""
        if not self._is_active:
            return self.original_open(file, mode, *args, **kwargs)
        
        # Only intercept write operations
        if 'w' not in mode and 'a' not in mode:
            return self.original_open(file, mode, *args, **kwargs)
        
        original_file = self.original_open(file, mode, *args, **kwargs)
        return self.InterceptedFile(original_file, file, self)
    
    def _intercepted_os_open(self, path, flags, *args, **kwargs):
        """Intercept os.open calls."""
        if not self._is_active:
            return self.original_os_open(path, flags, *args, **kwargs)

        # Check if it's a write operation
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            if not self._is_path_whitelisted(path):
                if self.non_whitelist_action == "ignore":
                    raise PermissionError(f"Write operation not allowed: {path}")
                # Handle encryption case
                return self._handle_non_whitelist_fd(path, flags, *args, **kwargs)
        
        fd = self.original_os_open(path, flags, *args, **kwargs)
        self._active_fds.add((fd, path))
        return fd

    def _intercepted_os_write(self, fd, data, *args, **kwargs):
        """Intercept os.write calls."""
        if not self._is_active:
            return self.original_os_write(fd, data, *args, **kwargs)

        # Check if this fd is being tracked
        fd_info = next((info for info in self._active_fds if info[0] == fd), None)
        if fd_info:
            _, path = fd_info
            if not self._is_path_whitelisted(path):
                if self.non_whitelist_action == "ignore":
                    raise PermissionError(f"Write operation not allowed: {path}")
                return self._handle_non_whitelist_write(fd, data, path)

        return self.original_os_write(fd, data, *args, **kwargs)

    def _intercepted_mmap(self, *args, **kwargs):
        """Intercept mmap.mmap calls."""
        if not self._is_active:
            return self.original_mmap(*args, **kwargs)

        fileno = args[0] if args else kwargs.get('fileno', -1)
        if fileno != -1:  # File-backed mmap
            fd_info = next((info for info in self._active_fds if info[0] == fileno), None)
            if fd_info:
                _, path = fd_info
                if not self._is_path_whitelisted(path):
                    raise PermissionError(f"Memory mapping not allowed for: {path}")

        mm = self.original_mmap(*args, **kwargs)
        return self._wrap_mmap(mm)

    def _wrap_mmap(self, mm):
        """Wrap mmap object to intercept writes."""
        original_write = mm.write
        def intercepted_write(data):
            if not self._is_active:
                return original_write(data)
            # Handle write interception
            # This is simplified - actual implementation would need more logic
            raise PermissionError("Direct mmap writes not allowed")
        mm.write = intercepted_write
        return mm

    @contextlib.contextmanager
    def activate(self):
        """Context manager to safely patch and restore all IO functions."""
        try:
            # Patch all IO functions
            builtins.open = self._intercepted_open
            os.open = self._intercepted_os_open
            os.write = self._intercepted_os_write
            mmap.mmap = self._intercepted_mmap
            self._is_active = True
            
            yield self
        finally:
            # Restore all original functions
            builtins.open = self.original_open
            os.open = self.original_os_open
            os.write = self.original_os_write
            mmap.mmap = self.original_mmap
            self._active_fds.clear()
            self._is_active = False
    
    def verify_hash(self, data: Union[str, bytes], hashed_filepath: str) -> bool:
        """Verify if data matches a previously saved hash.
        
        Args:
            data: The data to verify
            hashed_filepath: Path to the hashed file (.hash)
        
        Returns:
            bool: True if the data matches the hash
        """
        if not hashed_filepath.endswith('.hash'):
            raise ValueError("Hashed file must have .hash extension")
        
        if isinstance(data, str):
            data = data.encode()
        
        # Read the saved hash and salt
        with self.original_open(hashed_filepath, 'rb') as f:
            saved_salt = f.read(16)
            saved_hash = f.read()
        
        # Create hash with same salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=saved_salt,
            iterations=100000,
        )
        new_hash = kdf.derive(data)
        
        return saved_hash == new_hash 