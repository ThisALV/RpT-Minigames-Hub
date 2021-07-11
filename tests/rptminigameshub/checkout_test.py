from rptminigameshub.checkout import *
import pytest


class TestServerResponseParsing:
    """Unit tests for different parse_availability_response() test cases."""

    def test_not_enough_args(self):
        with pytest.raises(BadResponseSyntax):
            parse_availability_response("AVAILABILITY 1")  # 2nd arg for players max is missing

    def test_too_many_args(self):
        with pytest.raises(BadResponseSyntax):
            parse_availability_response("AVAILABILITY 1 2 Hello")  # 3rd arg should not be there

    def test_bad_command(self):
        with pytest.raises(BadResponseSyntax):
            parse_availability_response("SOMETHING_UNEXPECTED 1 2")  # Expected 1st word to be the AVAILABILITY command

    def test_invalid_players_count(self):
        with pytest.raises(BadResponseSyntax):
            parse_availability_response("AVAILABILITY Hello 2")  # Expected 1st arg to be an integer

    def test_invalid_players_max(self):
        with pytest.raises(BadResponseSyntax):
            parse_availability_response("AVAILABILITY 1 Hello")  # Expected 2nd arg to be an integer

    def test_everything_fine(self):
        assert parse_availability_response("AVAILABILITY 0 2") == (0, 2)
        assert parse_availability_response("AVAILABILITY 2 3") == (2, 3)
