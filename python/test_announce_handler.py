"""
Test suite for announce handler functionality
Tests that the announce handler properly integrates with RNS.Transport.register_announce_handler
"""

import sys
import os
import unittest
from unittest.mock import Mock, MagicMock, patch

# Add parent directory to path to import reticulum_wrapper
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock RNS and LXMF before importing reticulum_wrapper
sys.modules['RNS'] = MagicMock()
sys.modules['RNS.vendor'] = MagicMock()
sys.modules['RNS.vendor.platformutils'] = MagicMock()
sys.modules['LXMF'] = MagicMock()

# Now import after mocking
import reticulum_wrapper


class TestAnnounceHandler(unittest.TestCase):
    """Test the announce handler registration and functionality"""

    def setUp(self):
        """Set up test fixtures"""
        # Create a temporary storage path
        import tempfile
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_handler_has_aspect_filter_attribute(self):
        """
        Test that announce handler has required aspect_filter attribute.

        Per Reticulum docs: "Must be an object with an aspect_filter attribute"
        This is REQUIRED for RNS.Transport.register_announce_handler to work.
        """
        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        # Test with the lxmf.delivery handler (all handlers have same structure)
        handler = wrapper._announce_handlers["lxmf.delivery"]
        self.assertTrue(
            hasattr(handler, 'aspect_filter'),
            "Announce handler must have 'aspect_filter' attribute for RNS to call it"
        )

    def test_handler_has_received_announce_method(self):
        """
        Test that announce handler has required received_announce() callable.

        Per Reticulum docs: "and a received_announce(destination_hash,
        announced_identity, app_data) callable"
        """
        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        # Test with the lxmf.delivery handler
        handler = wrapper._announce_handlers["lxmf.delivery"]

        # The handler should have received_announce method
        self.assertTrue(
            hasattr(handler, 'received_announce'),
            "Announce handler must have 'received_announce' method"
        )

        # It should be callable
        self.assertTrue(
            callable(getattr(handler, 'received_announce', None)),
            "received_announce must be callable"
        )

    @patch('reticulum_wrapper.RNS')
    def test_handler_calls_underlying_callback(self, mock_rns):
        """
        Test that when received_announce is called, it invokes the actual handler.
        """
        # Mock RNS.Transport.hops_to to return 1
        mock_rns.Transport.hops_to.return_value = 1

        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        # Mock the internal handler to track calls
        wrapper._announce_handler = Mock()

        # Update the callback reference in the existing handler
        handler = wrapper._announce_handlers["lxmf.delivery"]
        handler.callback = wrapper._announce_handler

        # Simulate RNS calling our handler
        test_dest_hash = b'test_destination_hash_bytes'
        test_identity = Mock()
        test_identity.get_public_key = Mock(return_value=b'test_pubkey')
        test_app_data = b'test_app_data'

        # This simulates what RNS.Transport would do
        handler.received_announce(
            test_dest_hash,
            test_identity,
            test_app_data
        )

        # Verify our internal handler was called
        wrapper._announce_handler.assert_called_once()

    def test_aspect_filter_matches_handler_aspect(self):
        """
        Test that aspect_filter matches the handler's aspect.

        Each handler has a specific aspect_filter to receive only announces for that aspect.
        """
        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        # Verify each handler has the correct aspect_filter
        expected_aspects = ["lxmf.delivery", "lxmf.propagation", "call.audio", "nomadnetwork.node"]

        for aspect in expected_aspects:
            handler = wrapper._announce_handlers[aspect]
            self.assertEqual(
                handler.aspect_filter,
                aspect,
                f"Handler for {aspect} should have aspect_filter={aspect}"
            )

    def test_handler_structure_compatible_with_rns(self):
        """
        Integration test: Verify handler structure is compatible with RNS requirements.

        This tests the EXACT requirements from Reticulum's documentation.
        """
        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        # Test all registered handlers
        for aspect, handler in wrapper._announce_handlers.items():
            # Check all RNS requirements
            checks = {
                'has_aspect_filter': hasattr(handler, 'aspect_filter'),
                'has_received_announce': hasattr(handler, 'received_announce'),
                'received_announce_callable': callable(getattr(handler, 'received_announce', None)),
            }

            failures = [check for check, passed in checks.items() if not passed]

            self.assertEqual(
                [],
                failures,
                f"Handler for {aspect} fails RNS compatibility checks: {failures}"
            )


class TestAnnounceHandlerIntegration(unittest.TestCase):
    """Integration tests for announce handling flow"""

    def setUp(self):
        """Set up test fixtures"""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch('reticulum_wrapper.RNS')
    def test_announce_handler_stores_pending_announces(self, mock_rns):
        """
        Test that when an announce is received, it's stored in pending_announces.

        This tests the full flow:
        1. RNS calls handler.received_announce()
        2. Handler calls wrapper._announce_handler()
        3. Announce is added to pending_announces queue
        """
        # Mock RNS.Transport.hops_to to return 1
        mock_rns.Transport.hops_to.return_value = 1

        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        # Ensure pending_announces is empty
        self.assertEqual(len(wrapper.pending_announces), 0)

        # Simulate an announce being received
        test_dest_hash = b'test_dest_hash_123'
        test_identity = Mock()
        test_identity.get_public_key = Mock(return_value=b'test_pubkey')
        test_identity.hash = b'test_identity_hash'
        test_app_data = b'test_app_data'

        # Use one of the registered handlers
        handler = wrapper._announce_handlers["lxmf.delivery"]

        # Call the handler (simulating what RNS would do)
        handler.received_announce(
            test_dest_hash,
            test_identity,
            test_app_data
        )

        # Verify announce was stored
        self.assertEqual(
            len(wrapper.pending_announces),
            1,
            "Announce should be added to pending_announces queue"
        )

        # Verify announce structure
        stored_announce = wrapper.pending_announces[0]
        self.assertEqual(stored_announce['destination_hash'], test_dest_hash)
        self.assertEqual(stored_announce['app_data'], test_app_data)


class TestUmsgpackEdgeCases(unittest.TestCase):
    """
    Test umsgpack deserialization edge cases for propagation node announces.

    These tests verify that the msgpack upgrade (0.9.8 -> 0.9.10) doesn't break
    the propagation node stamp cost extraction at lines 1054-1057 of reticulum_wrapper.py:

        from RNS.vendor import umsgpack
        data = umsgpack.unpackb(app_data)
        stamp_cost_flexibility = int(data[5][1])
        peering_cost = int(data[5][2])
    """

    def setUp(self):
        """Set up test fixtures"""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch('reticulum_wrapper.LXMF')
    @patch('reticulum_wrapper.RNS')
    def test_successful_propagation_node_extraction(self, mock_rns, mock_lxmf):
        """Test successful extraction of stamp cost, flexibility, and peering cost"""
        mock_rns.Transport.hops_to.return_value = 1
        mock_lxmf.pn_stamp_cost_from_app_data.return_value = 16
        mock_lxmf.pn_announce_data_is_valid.return_value = True

        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        test_dest_hash = b'test_dest_hash_123'
        test_identity = Mock()
        test_identity.get_public_key = Mock(return_value=b'test_pubkey')
        test_app_data = b'propagation_node_app_data'

        # Mock umsgpack to return valid propagation node data structure
        with patch('RNS.vendor.umsgpack.unpackb', return_value=[
            None, None, None, None, None,
            [16, 2, 4]  # [stamp_cost, flexibility, peering_cost]
        ]):
            handler = wrapper._announce_handlers["lxmf.propagation"]
            handler.received_announce(test_dest_hash, test_identity, test_app_data)

        # Verify all costs were extracted correctly
        self.assertEqual(len(wrapper.pending_announces), 1)
        stored_announce = wrapper.pending_announces[0]
        self.assertEqual(stored_announce['stamp_cost'], 16)
        self.assertEqual(stored_announce['stamp_cost_flexibility'], 2)
        self.assertEqual(stored_announce['peering_cost'], 4)

    @patch('reticulum_wrapper.LXMF')
    @patch('reticulum_wrapper.RNS')
    def test_umsgpack_unpackb_raises_exception(self, mock_rns, mock_lxmf):
        """Test handler gracefully handles umsgpack.unpackb() raising exception"""
        mock_rns.Transport.hops_to.return_value = 1
        mock_lxmf.pn_stamp_cost_from_app_data.return_value = 16
        mock_lxmf.pn_announce_data_is_valid.return_value = True

        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        test_dest_hash = b'test_dest_hash_123'
        test_identity = Mock()
        test_identity.get_public_key = Mock(return_value=b'test_pubkey')
        test_app_data = b'malformed_msgpack_data'

        # Mock umsgpack.unpackb to raise exception
        with patch('RNS.vendor.umsgpack.unpackb', side_effect=Exception("Invalid msgpack data")):
            handler = wrapper._announce_handlers["lxmf.propagation"]
            # Should not raise - error is caught by except block
            handler.received_announce(test_dest_hash, test_identity, test_app_data)

        # Verify announce was stored but flexibility/peering_cost are None
        self.assertEqual(len(wrapper.pending_announces), 1)
        stored_announce = wrapper.pending_announces[0]
        self.assertIsNone(stored_announce['stamp_cost_flexibility'])
        self.assertIsNone(stored_announce['peering_cost'])

    @patch('reticulum_wrapper.LXMF')
    @patch('reticulum_wrapper.RNS')
    def test_umsgpack_index_out_of_bounds_data5_missing(self, mock_rns, mock_lxmf):
        """Test handler when data[5] doesn't exist (short array)"""
        mock_rns.Transport.hops_to.return_value = 1
        mock_lxmf.pn_stamp_cost_from_app_data.return_value = 16
        mock_lxmf.pn_announce_data_is_valid.return_value = True

        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        test_dest_hash = b'test_dest_hash_123'
        test_identity = Mock()
        test_identity.get_public_key = Mock(return_value=b'test_pubkey')
        test_app_data = b'short_array_data'

        # Mock umsgpack to return array with only 3 elements (no index 5)
        with patch('RNS.vendor.umsgpack.unpackb', return_value=[1, 2, 3]):
            handler = wrapper._announce_handlers["lxmf.propagation"]
            # Should not raise - IndexError caught by except block
            handler.received_announce(test_dest_hash, test_identity, test_app_data)

        # Verify announce was stored with None values
        self.assertEqual(len(wrapper.pending_announces), 1)
        stored_announce = wrapper.pending_announces[0]
        self.assertIsNone(stored_announce['stamp_cost_flexibility'])
        self.assertIsNone(stored_announce['peering_cost'])

    @patch('reticulum_wrapper.LXMF')
    @patch('reticulum_wrapper.RNS')
    def test_umsgpack_index_out_of_bounds_nested(self, mock_rns, mock_lxmf):
        """Test handler when data[5][1] or data[5][2] doesn't exist"""
        mock_rns.Transport.hops_to.return_value = 1
        mock_lxmf.pn_stamp_cost_from_app_data.return_value = 16
        mock_lxmf.pn_announce_data_is_valid.return_value = True

        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        test_dest_hash = b'test_dest_hash_123'
        test_identity = Mock()
        test_identity.get_public_key = Mock(return_value=b'test_pubkey')
        test_app_data = b'short_nested_data'

        # Mock umsgpack to return data[5] with only 1 element
        with patch('RNS.vendor.umsgpack.unpackb', return_value=[
            None, None, None, None, None,
            [16]  # Only stamp_cost, no flexibility or peering_cost
        ]):
            handler = wrapper._announce_handlers["lxmf.propagation"]
            handler.received_announce(test_dest_hash, test_identity, test_app_data)

        # Verify announce was stored with None values for missing indices
        self.assertEqual(len(wrapper.pending_announces), 1)
        stored_announce = wrapper.pending_announces[0]
        self.assertIsNone(stored_announce['stamp_cost_flexibility'])
        self.assertIsNone(stored_announce['peering_cost'])

    @patch('reticulum_wrapper.LXMF')
    @patch('reticulum_wrapper.RNS')
    def test_umsgpack_type_error_on_int_conversion(self, mock_rns, mock_lxmf):
        """Test handler when int() conversion fails (non-numeric value)"""
        mock_rns.Transport.hops_to.return_value = 1
        mock_lxmf.pn_stamp_cost_from_app_data.return_value = 16
        mock_lxmf.pn_announce_data_is_valid.return_value = True

        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        test_dest_hash = b'test_dest_hash_123'
        test_identity = Mock()
        test_identity.get_public_key = Mock(return_value=b'test_pubkey')
        test_app_data = b'non_numeric_data'

        # Mock umsgpack to return non-numeric values in the expected positions
        with patch('RNS.vendor.umsgpack.unpackb', return_value=[
            None, None, None, None, None,
            [16, "not_a_number", {"dict": "value"}]  # Can't convert to int
        ]):
            handler = wrapper._announce_handlers["lxmf.propagation"]
            handler.received_announce(test_dest_hash, test_identity, test_app_data)

        # Verify announce was stored - exception caught
        self.assertEqual(len(wrapper.pending_announces), 1)
        stored_announce = wrapper.pending_announces[0]
        # Due to exception, these will be None
        self.assertIsNone(stored_announce['stamp_cost_flexibility'])
        self.assertIsNone(stored_announce['peering_cost'])

    @patch('reticulum_wrapper.LXMF')
    @patch('reticulum_wrapper.RNS')
    def test_umsgpack_large_values(self, mock_rns, mock_lxmf):
        """Test handler with large int values at boundary"""
        mock_rns.Transport.hops_to.return_value = 1
        mock_lxmf.pn_stamp_cost_from_app_data.return_value = 999999
        mock_lxmf.pn_announce_data_is_valid.return_value = True

        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        test_dest_hash = b'test_dest_hash_123'
        test_identity = Mock()
        test_identity.get_public_key = Mock(return_value=b'test_pubkey')
        test_app_data = b'large_values_data'

        # Test with large but valid integer values
        large_flex = 2**31 - 1  # Max 32-bit signed int
        large_peer = 2**16      # Larger than typical values

        with patch('RNS.vendor.umsgpack.unpackb', return_value=[
            None, None, None, None, None,
            [999999, large_flex, large_peer]
        ]):
            handler = wrapper._announce_handlers["lxmf.propagation"]
            handler.received_announce(test_dest_hash, test_identity, test_app_data)

        # Verify large values are handled correctly
        self.assertEqual(len(wrapper.pending_announces), 1)
        stored_announce = wrapper.pending_announces[0]
        self.assertEqual(stored_announce['stamp_cost'], 999999)
        self.assertEqual(stored_announce['stamp_cost_flexibility'], large_flex)
        self.assertEqual(stored_announce['peering_cost'], large_peer)

    @patch('reticulum_wrapper.LXMF')
    @patch('reticulum_wrapper.RNS')
    def test_umsgpack_empty_app_data(self, mock_rns, mock_lxmf):
        """Test handler with empty app_data bytes"""
        mock_rns.Transport.hops_to.return_value = 1
        # Empty app_data should not trigger LXMF calls due to "if LXMF is not None and app_data" check

        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        test_dest_hash = b'test_dest_hash_123'
        test_identity = Mock()
        test_identity.get_public_key = Mock(return_value=b'test_pubkey')
        test_app_data = b''  # Empty bytes

        handler = wrapper._announce_handlers["lxmf.propagation"]
        handler.received_announce(test_dest_hash, test_identity, test_app_data)

        # Verify announce was stored but costs are None (no LXMF extraction attempted)
        self.assertEqual(len(wrapper.pending_announces), 1)
        stored_announce = wrapper.pending_announces[0]
        self.assertIsNone(stored_announce['stamp_cost'])
        self.assertIsNone(stored_announce['stamp_cost_flexibility'])
        self.assertIsNone(stored_announce['peering_cost'])

    @patch('reticulum_wrapper.LXMF')
    @patch('reticulum_wrapper.RNS')
    def test_pn_announce_data_is_valid_returns_false(self, mock_rns, mock_lxmf):
        """Test that umsgpack is not called when pn_announce_data_is_valid returns False"""
        mock_rns.Transport.hops_to.return_value = 1
        mock_lxmf.pn_stamp_cost_from_app_data.return_value = 16
        mock_lxmf.pn_announce_data_is_valid.return_value = False  # Data not valid

        wrapper = reticulum_wrapper.ReticulumWrapper(self.temp_dir)

        test_dest_hash = b'test_dest_hash_123'
        test_identity = Mock()
        test_identity.get_public_key = Mock(return_value=b'test_pubkey')
        test_app_data = b'invalid_pn_data'

        # umsgpack should NOT be called since pn_announce_data_is_valid returns False
        with patch('RNS.vendor.umsgpack.unpackb') as mock_unpackb:
            handler = wrapper._announce_handlers["lxmf.propagation"]
            handler.received_announce(test_dest_hash, test_identity, test_app_data)

            # Verify umsgpack was not called
            mock_unpackb.assert_not_called()

        # Verify announce was stored with stamp_cost but no flexibility/peering
        self.assertEqual(len(wrapper.pending_announces), 1)
        stored_announce = wrapper.pending_announces[0]
        self.assertEqual(stored_announce['stamp_cost'], 16)
        self.assertIsNone(stored_announce['stamp_cost_flexibility'])
        self.assertIsNone(stored_announce['peering_cost'])


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
