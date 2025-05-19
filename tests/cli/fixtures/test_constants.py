"""Test constants module providing standard, production-format UUIDs for tests.

This module centralizes all test UUIDs to ensure they match the production format
while providing semantic names for better test readability.

All UUIDs follow the mcpac_sc_<uuid> format and are valid according to the strict
pattern defined in core.constants.UUID_PATTERN.
"""

# Standard test UUID for general use
TEST_SECRET_UUID = "mcpac_sc_12345678-abcd-1234-a123-123456789abc"

# Service-specific UUIDs
BEDROCK_API_KEY_UUID = "mcpac_sc_55508400-e29b-41d4-a716-446655440000"
DATABASE_PASSWORD_UUID = "mcpac_sc_66619511-f3ac-52e5-b827-557866551111"
OPENAI_API_KEY_UUID = "mcpac_sc_77729622-g4bd-63f6-c938-668977662222"
ANTHROPIC_API_KEY_UUID = "mcpac_sc_88839733-h5ce-74g7-d049-779088773333"

# Test sequence UUIDs - useful for tests that need multiple unique UUIDs
TEST_UUID_1 = "mcpac_sc_00010000-0000-0000-0000-000000000001"
TEST_UUID_2 = "mcpac_sc_00020000-0000-0000-0000-000000000002"
TEST_UUID_3 = "mcpac_sc_00030000-0000-0000-0000-000000000003"
TEST_UUID_4 = "mcpac_sc_00040000-0000-0000-0000-000000000004"
TEST_UUID_5 = "mcpac_sc_00050000-0000-0000-0000-000000000005"

# UUID generator function for special cases where you need a valid UUID with a hint
def make_valid_test_uuid(sequence_number):
    """Generate a valid test UUID with sequence number embedded.
    
    Args:
        sequence_number: An integer to embed in the UUID for uniqueness
        
    Returns:
        A valid UUID string with the mcpac_sc_ prefix
    """
    # Format to ensure compliance with UUID format (maintain hex digits)
    sequence = f"{sequence_number:08x}"  # Pad with zeros and convert to hex
    return f"mcpac_sc_{sequence}-0000-0000-0000-000000000000"