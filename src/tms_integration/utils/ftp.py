import ftplib
import logging
import os

from pydantic import BaseModel
from pydantic.dataclasses import dataclass

logger = logging.getLogger(__name__)


class FtpConfig(BaseModel):
    """FTP configuration"""

    host: str
    port: int = 21
    username: str | None = None
    password: str | None = None
    timeout: int = 30

    class Config:
        arbitrary_types_allowed = True


@dataclass
class FtpBase:
    """Base class for FTP operations"""

    config: FtpConfig

    def _get_connection(self) -> ftplib.FTP:
        """
        Create and return an FTP connection

        Returns:
            ftplib.FTP: Connected FTP client

        Raises:
            ftplib.all_errors: If connection fails
        """
        ftp = ftplib.FTP()
        ftp.connect(
            host=self.config.host, port=self.config.port, timeout=self.config.timeout
        )
        ftp.login(user=self.config.username, passwd=self.config.password)
        return ftp

    def import_file(self, source_filepath: str, dest_path: str) -> None:
        """
        Upload a file from local filesystem to FTP server

        Args:
            source_filepath: The local path of the file to be uploaded
            dest_path: The destination folder on the FTP server

        Raises:
            FileNotFoundError: If source file doesn't exist
            ftplib.all_errors: If FTP operation fails
        """
        if not os.path.exists(source_filepath):
            raise FileNotFoundError(f"Source file not found: {source_filepath}")

        filename = os.path.basename(source_filepath)

        ftp = None
        try:
            ftp = self._get_connection()
            ftp.cwd(dest_path)

            with open(source_filepath, "rb") as f:
                ftp.storbinary(f"STOR {filename}", f)

            logger.info(f"Uploaded {filename} to {dest_path}/{filename}")

        except ftplib.all_errors as e:
            logger.error(f"FTP upload failed for {filename}: {e}")
            raise
        finally:
            if ftp:
                ftp.quit()

    def export_file(self, remote_filepath: str, local_filepath: str) -> None:
        """
        Download a file from FTP server to local filesystem

        Args:
            remote_filepath: The file path on the FTP server
            local_filepath: The local path where the file will be saved

        Raises:
            ftplib.all_errors: If FTP operation fails
        """
        ftp = None
        try:
            ftp = self._get_connection()

            with open(local_filepath, "wb") as f:
                ftp.retrbinary(f"RETR {remote_filepath}", f.write)

            logger.info(f"Downloaded {remote_filepath} to {local_filepath}")

        except ftplib.all_errors as e:
            logger.error(f"FTP download failed for {remote_filepath}: {e}")
            raise
        finally:
            if ftp:
                ftp.quit()

    def get_all_files(self, remote_folder: str) -> list:
        """
        List all files in a remote FTP folder

        Args:
            remote_folder: The remote folder path

        Returns:
            list: List of file paths in the remote folder

        Raises:
            ftplib.all_errors: If FTP operation fails
        """
        remote_files = []
        ftp = None

        try:
            ftp = self._get_connection()
            ftp.cwd(remote_folder)

            files = ftp.nlst()
            for filename in files:
                remote_filepath = f"{remote_folder}/{filename}"
                remote_files.append(remote_filepath)

            logger.info(f"Listed {len(remote_files)} files in {remote_folder}")

        except ftplib.all_errors as e:
            logger.error(f"FTP list failed for {remote_folder}: {e}")
            raise
        finally:
            if ftp:
                ftp.quit()

        return remote_files

    def delete_file(self, remote_filepath: str) -> None:
        """
        Delete a file from FTP server

        Args:
            remote_filepath: The file path on the FTP server

        Raises:
            ftplib.all_errors: If FTP operation fails
        """
        ftp = None
        try:
            ftp = self._get_connection()

            # Check if file exists
            try:
                ftp.size(remote_filepath)
            except ftplib.error_temp:
                logger.warning(f"File not found on FTP: {remote_filepath}")
                return

            ftp.delete(remote_filepath)
            logger.info(f"Deleted {remote_filepath}")

        except ftplib.all_errors as e:
            logger.error(f"FTP delete failed for {remote_filepath}: {e}")
            raise
        finally:
            if ftp:
                ftp.quit()

    def create_folder(self, remote_folder: str) -> None:
        """
        Create a folder on FTP server

        Args:
            remote_folder: The folder path to create

        Raises:
            ftplib.all_errors: If FTP operation fails
        """
        ftp = None
        try:
            ftp = self._get_connection()
            ftp.mkd(remote_folder)
            logger.info(f"Created folder {remote_folder}")

        except ftplib.error_perm as e:
            if "File exists" in str(e):
                logger.debug(f"Folder already exists: {remote_folder}")
            else:
                logger.error(f"FTP create folder failed: {e}")
                raise
        except ftplib.all_errors as e:
            logger.error(f"FTP create folder failed: {e}")
            raise
        finally:
            if ftp:
                ftp.quit()
