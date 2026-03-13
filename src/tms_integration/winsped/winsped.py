import logging
import os
import tempfile
from pathlib import Path

from pydantic.dataclasses import dataclass

from src.tms_integration.utils.ftp import FtpBase, FtpConfig
from src.tms_integration.winsped.models.lisin import LisIn
from tms_integration.winsped.models import LisInPosition

logger = logging.getLogger(__name__)


@dataclass
class LisWinSped(FtpBase):
    """
    LisWinSped integration for uploading location and driver data to FTP server

    Inherits all FTP operations from FtpBase and adds business logic
    specific to WinSped integration.
    """

    import_dest_folder: str

    def import_to_ftp(self, payload: LisIn, message_number: str, country: str) -> None:
        """
        Generate WinSped format file and upload to FTP server

        Args:
            payload: LisIn object containing location/driver data
            message_number: Message identifier (e.g., "15" for positions)
            country: Country code (e.g., "UA", "PL")

        Example:
            >>> lis_winsped = LisWinSped(
            ...     config=FtpConfig(host="...", username="...", password="..."),
            ...     import_dest_folder="/imports",
            ... )
            >>> payload = LisInPosition()
            >>> payload.records = [...]
            >>> lis_winsped.import_location(payload, "15", "UA")
        """
        filename = f"{message_number}_{country}.txt"
        filepath = os.path.join(tempfile.gettempdir(), filename)

        try:
            with open(filepath, mode="w", encoding="cp1252") as f:
                f.write(payload.generate_txt())

            # save locally
            # local_path = Path(__file__).resolve().parent.parent.parent / filename
            # with open(local_path, "w", encoding="cp1252") as f:
            #    f.write(payload.generate_txt())
            # print(f"Saved locally: {local_path}")

            self.import_file(filepath, self.import_dest_folder)

            logger.info(
                f"Successfully imported {filename} to {self.import_dest_folder} "
                f"({country} - {len(payload.records)} records)"
            )

        except FileNotFoundError as e:
            logger.error(f"Failed to create temporary file: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to import location for {country}: {e}")
            raise
        finally:
            if os.path.exists(filepath):
                try:
                    os.unlink(filepath)
                except OSError as e:
                    logger.warning(f"Failed to clean up temporary file {filepath}: {e}")

    def check_import_folder_exists(self) -> bool:
        """
        Check if the import destination folder exists on FTP server

        Returns:
            bool: True if folder exists, False otherwise
        """
        try:
            files = self.get_all_files(self.import_dest_folder)
            logger.debug(f"Import folder exists: {self.import_dest_folder}")
            return True
        except Exception as e:
            logger.warning(f"Import folder check failed: {e}")
            return False

    def create_import_folder_if_needed(self) -> None:
        """
        Create import destination folder if it doesn't exist

        This is useful for first-time setup
        """
        try:
            self.create_folder(self.import_dest_folder)
        except Exception as e:
            logger.warning(f"Could not create import folder: {e}")
