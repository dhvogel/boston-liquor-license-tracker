"""
Comprehensive unit tests for extract_entity.py
"""

import pytest
import json
import os
import tempfile
import shutil
from unittest.mock import patch, mock_open, MagicMock
from datetime import datetime

# Handle optional dependencies gracefully
try:
    from dateutil.relativedelta import relativedelta
except ImportError:
    # Create a mock relativedelta for testing if not available
    class MockRelativeDelta:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        def __add__(self, other):
            return other
        def __radd__(self, other):
            return other
    relativedelta = MockRelativeDelta

from extract_entity import (
    parse_entity,
    extract_hearing_date,
    extract_entities_from_pdf,
    write_to_file,
    process_pdf
)


class TestParseEntity:
    """Test cases for the parse_entity function."""
    
    def test_parse_entity_complete_data(self):
        """Test parsing entity with all fields present."""
        entity_text = """1. ABC Restaurant Inc.
Doing Business As: The Best Diner
123 Main Street, Boston, MA 02101
License #: ABC-123
Applied for All-Alcoholic Beverages Common Victualler 7 Day License
test_file.pdf"""
        
        result = parse_entity(entity_text)
        
        assert result["entity_number"] == "1"
        assert result["business_name"] == "ABC Restaurant Inc."
        assert result["dba_name"] == "The Best Diner"
        assert result["address"] == "123 Main Street, Boston, MA 02101"
        assert result["zipcode"] == "02101"
        assert result["license_number"] == "ABC-123"
        assert result["alcohol_type"] == "All Alcoholic Beverages"
        assert result["file_name"] == "test_file.pdf"
    
    def test_parse_entity_wines_and_malt(self):
        """Test parsing entity with wines and malt beverages."""
        entity_text = """2. XYZ Cafe LLC
456 Oak Avenue, Cambridge, MA 02139
Applied for Wines and Malt Beverages Common Victualler 7 Day License
test_file.pdf"""
        
        result = parse_entity(entity_text)
        
        assert result["entity_number"] == "2"
        assert result["business_name"] == "XYZ Cafe LLC"
        assert result["address"] == "456 Oak Avenue, Cambridge, MA 02139"
        assert result["zipcode"] == "02139"
        assert result["alcohol_type"] == "Wines and Malt Beverages"
    
    def test_parse_entity_minimal_data(self):
        """Test parsing entity with minimal required data."""
        entity_text = """3. Simple Business
test_file.pdf"""
        
        result = parse_entity(entity_text)
        
        assert result["entity_number"] == "3"
        assert result["business_name"] == "Simple Business"
        assert result["dba_name"] is None
        assert result["address"] is None
        assert result["zipcode"] is None
        assert result["license_number"] is None
        assert result["alcohol_type"] is None
        assert result["file_name"] == "test_file.pdf"
    
    def test_parse_entity_empty_input(self):
        """Test parsing empty entity."""
        result = parse_entity("")
        
        # All fields should be None
        for key in result:
            assert result[key] is None
    
    def test_parse_entity_whitespace_only(self):
        """Test parsing entity with only whitespace."""
        result = parse_entity("   \n\t  \n  ")
        
        # All fields should be None
        for key in result:
            assert result[key] is None
    
    def test_parse_entity_no_entity_number(self):
        """Test parsing entity without entity number."""
        entity_text = """Some Business Name
123 Main St, Boston, MA 02101
test_file.pdf"""
        
        result = parse_entity(entity_text)
        
        assert result["entity_number"] is None
        assert result["business_name"] is None  # Won't be parsed without entity number
        assert result["file_name"] == "test_file.pdf"
    
    def test_parse_entity_dba_variations(self):
        """Test different DBA format variations."""
        entity_text = """1. Main Business
Doing Business As: DBA Name Here
test_file.pdf"""
        
        result = parse_entity(entity_text)
        assert result["dba_name"] == "DBA Name Here"
        
        # Test case insensitive
        entity_text2 = """1. Main Business
DOING BUSINESS AS: Another DBA
test_file.pdf"""
        
        result2 = parse_entity(entity_text2)
        assert result2["dba_name"] == "Another DBA"
    
    def test_parse_entity_license_number_variations(self):
        """Test different license number formats."""
        test_cases = [
            ("License #: ABC123", "ABC123"),
            ("License#: DEF-456", "DEF-456"),
            ("LICENSE #: GHI789", "GHI789"),
            ("license #: jkl-012", "jkl-012")
        ]
        
        for license_text, expected in test_cases:
            entity_text = f"""1. Test Business
{license_text}
test_file.pdf"""
            result = parse_entity(entity_text)
            assert result["license_number"] == expected
    
    def test_parse_entity_address_with_zipcode(self):
        """Test address parsing with various zipcode formats."""
        test_cases = [
            ("123 Main St, Boston, MA 02101", "02101"),
            ("456 Oak Ave, Cambridge, MA 02139", "02139"),
            ("789 Pine Rd, Somerville, MA 02144", "02144")
        ]
        
        for address, expected_zip in test_cases:
            entity_text = f"""1. Test Business
{address}
test_file.pdf"""
            result = parse_entity(entity_text)
            assert result["address"] == address
            assert result["zipcode"] == expected_zip


class TestExtractHearingDate:
    """Test cases for the extract_hearing_date function."""
    
    @patch('fitz.open')
    def test_extract_hearing_date_valid(self, mock_fitz_open):
        """Test extracting valid hearing date."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Meeting held on January 15, 2024 at City Hall"
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz_open.return_value = mock_doc
        
        result = extract_hearing_date("test.pdf")
        
        expected_date = datetime(2024, 1, 15)
        assert result == expected_date
        mock_fitz_open.assert_called_once_with("test.pdf")
    
    @patch('fitz.open')
    def test_extract_hearing_date_different_formats(self, mock_fitz_open):
        """Test extracting dates in different valid formats."""
        test_cases = [
            ("December 31, 2023", datetime(2023, 12, 31)),
            ("March 5, 2024", datetime(2024, 3, 5)),
            ("July 4, 2025", datetime(2025, 7, 4))
        ]
        
        for date_text, expected_date in test_cases:
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_page.get_text.return_value = f"Meeting on {date_text}"
            mock_doc.__getitem__.return_value = mock_page
            mock_fitz_open.return_value = mock_doc
            
            result = extract_hearing_date("test.pdf")
            assert result == expected_date
    
    @patch('fitz.open')
    def test_extract_hearing_date_no_date_found(self, mock_fitz_open):
        """Test when no date is found in PDF."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "No date information here"
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz_open.return_value = mock_doc
        
        with pytest.raises(ValueError, match="Could not find date in the pdf"):
            extract_hearing_date("test.pdf")
    
    @patch('fitz.open')
    def test_extract_hearing_date_invalid_date_format(self, mock_fitz_open):
        """Test when date format is invalid."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Meeting on February 32, 2024"  # Invalid date
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz_open.return_value = mock_doc
        
        with pytest.raises(ValueError, match="Could not conver date string to iso format"):
            extract_hearing_date("test.pdf")
    
    @patch('fitz.open')
    def test_extract_hearing_date_file_error(self, mock_fitz_open):
        """Test when PDF file cannot be opened."""
        mock_fitz_open.side_effect = Exception("File not found")
        
        with pytest.raises(Exception, match="File not found"):
            extract_hearing_date("nonexistent.pdf")


class TestExtractEntitiesFromPdf:
    """Test cases for the extract_entities_from_pdf function."""
    
    @patch('fitz.open')
    @patch('os.path.basename')
    def test_extract_entities_basic(self, mock_basename, mock_fitz_open):
        """Test basic entity extraction from PDF."""
        mock_basename.return_value = "test.pdf"
        
        # Mock PDF document structure
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_page = MagicMock()
        mock_doc.load_page.return_value = mock_page
        
        # Mock page structure with entities
        mock_page_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [
                                {"text": "Transactional Hearing", "flags": 0},
                            ]
                        },
                        {
                            "spans": [
                                {"text": "1. Test Business", "flags": 20},
                            ]
                        },
                        {
                            "spans": [
                                {"text": "123 Main St", "flags": 0},
                            ]
                        },
                        {
                            "spans": [
                                {"text": "2. Another Business", "flags": 20},
                            ]
                        },
                        {
                            "spans": [
                                {"text": "456 Oak Ave", "flags": 0},
                            ]
                        }
                    ]
                }
            ]
        }
        
        mock_page.get_text.return_value = mock_page_dict
        mock_fitz_open.return_value = mock_doc
        
        result = extract_entities_from_pdf("test.pdf")
        
        assert len(result) == 2
        assert "1. Test Business" in result[0]
        assert "123 Main St" in result[0]
        assert "test.pdf" in result[0]
        assert "2. Another Business" in result[1]
        assert "456 Oak Ave" in result[1]
        assert "test.pdf" in result[1]
    
    @patch('fitz.open')
    def test_extract_entities_file_not_found(self, mock_fitz_open):
        """Test handling when PDF file cannot be opened."""
        mock_fitz_open.side_effect = Exception("File not found")
        
        with pytest.raises(SystemExit):
            extract_entities_from_pdf("nonexistent.pdf")
    
    @patch('fitz.open')
    @patch('os.path.basename')
    def test_extract_entities_no_transactional_section(self, mock_basename, mock_fitz_open):
        """Test when no Transactional Hearing section is found."""
        mock_basename.return_value = "test.pdf"
        
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_page = MagicMock()
        mock_doc.load_page.return_value = mock_page
        
        mock_page_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [
                                {"text": "Some other content", "flags": 0},
                            ]
                        }
                    ]
                }
            ]
        }
        
        mock_page.get_text.return_value = mock_page_dict
        mock_fitz_open.return_value = mock_doc
        
        result = extract_entities_from_pdf("test.pdf")
        
        assert len(result) == 0


class TestWriteToFile:
    """Test cases for the write_to_file function."""
    
    def test_write_to_file_new_file(self):
        """Test writing to a new file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test directory structure
            test_scripts_dir = os.path.join(temp_dir, "scripts")
            test_data_dir = os.path.join(temp_dir, "data")
            os.makedirs(test_scripts_dir)
            os.makedirs(test_data_dir)
            
            # Change to test scripts directory
            original_cwd = os.getcwd()
            os.chdir(test_scripts_dir)
            
            try:
                test_data = [
                    {"index": None, "entity_number": "1", "business_name": "Test Business"}
                ]
                
                write_to_file(test_data)
                
                # Check if file was created and data written
                output_file = "../data/application_data.json"
                assert os.path.exists(output_file)
                
                with open(output_file, "r") as f:
                    written_data = json.load(f)
                
                assert len(written_data) == 1
                assert written_data[0]["entity_number"] == "1"
                assert written_data[0]["business_name"] == "Test Business"
                
            finally:
                os.chdir(original_cwd)
    
    def test_write_to_file_append_to_existing(self):
        """Test appending to existing file with index assignment."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test directory structure
            test_scripts_dir = os.path.join(temp_dir, "scripts")
            test_data_dir = os.path.join(temp_dir, "data")
            os.makedirs(test_scripts_dir)
            os.makedirs(test_data_dir)
            
            original_cwd = os.getcwd()
            os.chdir(test_scripts_dir)
            
            try:
                output_file = "../data/application_data.json"
                
                # Create existing data
                existing_data = [
                    {"index": 1, "entity_number": "1", "business_name": "Existing Business"}
                ]
                
                with open(output_file, "w") as f:
                    json.dump(existing_data, f)
                
                # New data to append
                new_data = [
                    {"index": None, "entity_number": "2", "business_name": "New Business"}
                ]
                
                write_to_file(new_data)
                
                # Check combined data
                with open(output_file, "r") as f:
                    all_data = json.load(f)
                
                assert len(all_data) == 2
                assert all_data[0]["index"] == 1
                assert all_data[1]["index"] == 2
                assert all_data[1]["entity_number"] == "2"
                
            finally:
                os.chdir(original_cwd)
    
    def test_write_to_file_empty_existing_file(self):
        """Test writing to empty existing file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test directory structure
            test_scripts_dir = os.path.join(temp_dir, "scripts")
            test_data_dir = os.path.join(temp_dir, "data")
            os.makedirs(test_scripts_dir)
            os.makedirs(test_data_dir)
            
            original_cwd = os.getcwd()
            os.chdir(test_scripts_dir)
            
            try:
                output_file = "../data/application_data.json"
                
                # Create empty file
                with open(output_file, "w") as f:
                    f.write("")
                
                test_data = [
                    {"index": None, "entity_number": "1", "business_name": "Test Business"}
                ]
                
                write_to_file(test_data)
                
                with open(output_file, "r") as f:
                    written_data = json.load(f)
                
                assert len(written_data) == 1
                assert written_data[0]["entity_number"] == "1"
                
            finally:
                os.chdir(original_cwd)


class TestProcessPdf:
    """Test cases for the process_pdf function."""
    
    @patch('extract_entity.extract_hearing_date')
    @patch('extract_entity.extract_entities_from_pdf')
    @patch('extract_entity.write_to_file')
    @patch('os.path.isfile')
    def test_process_pdf_success(self, mock_isfile, mock_write, mock_extract_entities, mock_extract_date):
        """Test successful PDF processing."""
        mock_isfile.return_value = True
        mock_extract_date.return_value = datetime(2024, 1, 15)
        mock_extract_entities.return_value = [
            "1. Test Business\nApplied for All-Alcoholic Beverages Common Victualler 7 Day License\ntest.pdf"
        ]
        
        result = process_pdf("test.pdf")
        
        assert len(result) == 1
        assert result[0]["entity_number"] == "1"
        assert result[0]["business_name"] == "Test Business"
        assert result[0]["alcohol_type"] == "All Alcoholic Beverages"
        assert result[0]["status"] == "Deferred"
        assert result[0]["minutes_date"] == "2024-01-15"
        assert result[0]["application_expiration_date"] == "2025-01-15"
        
        mock_write.assert_called_once()
    
    @patch('extract_entity.extract_hearing_date')
    @patch('extract_entity.extract_entities_from_pdf')
    @patch('os.path.isfile')
    def test_process_pdf_seeding_mode(self, mock_isfile, mock_extract_entities, mock_extract_date):
        """Test PDF processing in seeding mode."""
        mock_isfile.return_value = True
        mock_extract_date.return_value = datetime(2024, 1, 15)
        mock_extract_entities.return_value = [
            "1. Test Business\nApplied for Wines and Malt Beverages Common Victualler 7 Day License\ntest.pdf"
        ]
        
        with patch('extract_entity.write_to_file') as mock_write:
            result = process_pdf("test.pdf", "seeding")
            
            assert len(result) == 1
            assert result[0]["alcohol_type"] == "Wines and Malt Beverages"
            mock_write.assert_not_called()  # Should not write in seeding mode
    
    @patch('os.path.isfile')
    def test_process_pdf_file_not_found(self, mock_isfile):
        """Test handling when PDF file doesn't exist."""
        mock_isfile.return_value = False
        
        with pytest.raises(SystemExit):
            process_pdf("nonexistent.pdf")
    
    @patch('extract_entity.extract_hearing_date')
    @patch('extract_entity.extract_entities_from_pdf')
    @patch('extract_entity.write_to_file')
    @patch('os.path.isfile')
    def test_process_pdf_date_extraction_error(self, mock_isfile, mock_write, mock_extract_entities, mock_extract_date):
        """Test handling when date extraction fails."""
        mock_isfile.return_value = True
        mock_extract_date.side_effect = ValueError("Could not find date")
        mock_extract_entities.return_value = [
            "1. Test Business\nApplied for All-Alcoholic Beverages Common Victualler 7 Day License\ntest.pdf"
        ]
        
        # Should not raise exception, but continue processing
        result = process_pdf("test.pdf")
        
        # Should still process entities but without date info
        assert len(result) == 1
        assert result[0]["minutes_date"] is None
        assert result[0]["application_expiration_date"] is None
    
    @patch('extract_entity.extract_hearing_date')
    @patch('extract_entity.extract_entities_from_pdf')
    @patch('extract_entity.write_to_file')
    @patch('os.path.isfile')
    def test_process_pdf_no_matching_entities(self, mock_isfile, mock_write, mock_extract_entities, mock_extract_date):
        """Test when no entities match alcohol type criteria."""
        mock_isfile.return_value = True
        mock_extract_date.return_value = datetime(2024, 1, 15)
        mock_extract_entities.return_value = [
            "1. Test Business\nSome other license type\ntest.pdf"
        ]
        
        result = process_pdf("test.pdf")
        
        assert len(result) == 0  # No matching entities
        mock_write.assert_called_once_with([])  # Empty list written


if __name__ == "__main__":
    pytest.main([__file__, "-v"])