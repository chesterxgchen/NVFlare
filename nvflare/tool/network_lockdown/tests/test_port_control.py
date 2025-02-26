import unittest
import socket
import ssl
from ..port_control.port_manager import PortManager, PortStatus
from ..port_control.protocol_valid import ProtocolValidator, ProtocolType

class TestPortControl(unittest.TestCase):
    def setUp(self):
        self.port_manager = PortManager()
        self.protocol_validator = ProtocolValidator()
        
    def test_port_management(self):
        # Test default allowed ports
        for port in PortManager.DEFAULT_ALLOWED_PORTS:
            self.assertTrue(self.port_manager.is_allowed(port))
            
        # Test blocking port
        test_port = 8002
        self.port_manager.block_port(test_port)
        self.assertFalse(self.port_manager.is_allowed(test_port))
        
        # Test allowing new port
        new_port = 9000
        self.port_manager.allow_port(new_port)
        self.assertTrue(self.port_manager.is_allowed(new_port))
        
    def test_connection_tracking(self):
        test_port = 8002
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Track connection
        self.port_manager.track_connection(test_port, sock)
        active_conns = self.port_manager.get_active_connections(test_port)
        self.assertIsNotNone(active_conns)
        self.assertIn(sock, active_conns)
        
        # Untrack connection
        self.port_manager.untrack_connection(test_port, sock)
        active_conns = self.port_manager.get_active_connections(test_port)
        self.assertIsNone(active_conns)
        
    def test_protocol_validation(self):
        # Test ML protocol validation
        self.assertTrue(
            self.protocol_validator.validate_ml_protocol('train', 512 * 1024))
        self.assertFalse(
            self.protocol_validator.validate_ml_protocol('invalid', 1024))
        
        # Test attestation validation
        valid_message = {
            'nonce': 'test_nonce',
            'timestamp': 100,
            'signature': 'test_sig'
        }
        self.assertTrue(
            self.protocol_validator.validate_attestation(valid_message))
        
        invalid_message = {
            'nonce': 'test_nonce'
            # Missing required fields
        }
        self.assertFalse(
            self.protocol_validator.validate_attestation(invalid_message))

if __name__ == '__main__':
    unittest.main() 