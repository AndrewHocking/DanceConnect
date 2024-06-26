# Path: cloud/cdn.py
from flask import flash
import requests
import json
import uuid
import os
import shutil
from PIL import Image
from werkzeug.utils import secure_filename
# from ...instance.config import Config


# TODO: HERE TO MODIFY ACCEPTED FILE FORMATS
ALLOWED_EXTENSIONS = ("png", "gif", "jpeg", "svg", "jpg")

TEMP_FOLDER = './website/cloud/temp'

MAX_FILE_SIZE = 1024 * 1024 * 10  # 10MB

# https://stackoverflow.com/a/32623308
SECRETS = os.path.join(os.path.split(
    os.path.split(os.path.dirname(__file__))[0])[0]) + "/secrets/keys.json"


class CDN:
    """
    A class that represents a CDN (Content Delivery Network) object. This class is used to upload and download
    files from cloudflare.

    Notes:
    I did not implement List images V2 because we should never need to list all images in the CDN. If we do and there is a
    lot of pictues, then it could cause unessesary load on the server.

    Methods:
        upload: Uploads a file to cloudflare's image CDN.
        download: Downloads a file from cloudflare's image CDN.
        delete: Deletes a file from cloudflare's image CDN.
        get_image_details: Gets a link to a file from cloudflare's image CDN.
        download_original: Downloads the original file from cloudflare's image CDN and saves it within a temporary folder.
        empty_temp_folder: Empties the temporary folder used to store downloaded files.
        _error_message: Returns a dictionary with an error message.

    Attributes:
        _key (str): The key used to authenticate with cloudflare's image CDN.
        _account_hash (str): The account hash used to authenticate with cloudflare's image CDN.
    """

    _key: str
    _account_hash: str

    def __init__(self):
        """
        The constructor for the CDN class. It reads the keys from the secrets folder and stores them in the class attributes.

        Returns:
            bool: True if the keys were read successfully, False otherwise.
        """
        try:
            with open(SECRETS, "r") as file:
                data = json.load(file)
                self._key = data["cloudflare"]["cdn_key"]
                self._account_hash = data["cloudflare"]["account_hash"]
                file.close()
        except Exception:
            print("ERROR: Failed to read keys from secrets folder")

    def upload(self, path: str) -> dict:
        """
        Uploads a file to cloudflare's image CDN.

        THIS FUNCTION IS NOT ASYNCHRONOUS. It will block the thread until the file is uploaded.

        This function will strip all the metadata from the image before uploading it to the CDN.

        Supported file formats: PNG, GIF, JPEG, and SVG.
        Supported file sizes: Up to 10MB.
        Supported image dimention: 12'000 pixels on the longest side.
        Supported image area: 100 MegaPixels. (ex. 10'000 x 10'000 pixels)
        Supported metadata: 10MB of metadata.
        Animated GIFs, including all frames, are limited to 100 megapixels (MP).

        To access image ID: ["result"]["id"]
        To access image URL: ["result"]["variants"][0]

        Response example:
        {
        "errors": [],
        "messages": [],
        "result": {
            "filename": "logo.png",
            "id": "107b9558-dd06-4bbd-5fef-9c2c16bb7900",
            "meta": {
            "key": "value"
            },
            "requireSignedURLs": true,
            "uploaded": "2014-01-02T02:20:00.123Z",
            "variants": [
            "https://imagedelivery.net/MTt4OTd0b0w5aj/107b9558-dd06-4bbd-5fef-9c2c16bb7900/thumbnail",
            "https://imagedelivery.net/MTt4OTd0b0w5aj/107b9558-dd06-4bbd-5fef-9c2c16bb7900/hero",
            "https://imagedelivery.net/MTt4OTd0b0w5aj/107b9558-dd06-4bbd-5fef-9c2c16bb7900/original"
            ]
        },
        "success": true
        }

        Args:
            path (str): The path to the file to upload.

        Returns:
            dict: A dictionary containing the response from cloudflare's image CDN or a dictionary containing an error message.
        """
        try:
            # strip metadata, this ensures there is no more than 10MB of metadata
            # we don't need the metadata anyways
            # from: https://stackoverflow.com/a/72247130
            img = Image.open(path)
            if "exif" in img.info:
                del img.info["exif"]  # Strip just EXIF data
            img.save(path, quality="keep")
            # reopen the image to update the image object
            img = Image.open(path)

            # check file attributes
            width, height = img.size
            if width > 12000:
                return self._error_message("Image width is greater than 12000 pixels")
            if height > 12000:
                return self._error_message("Image height is greater than 12000 pixels")
            if width * height > 100000000:
                return self._error_message("Image area is greater than 100 MegaPixels")
            if os.path.getsize(path) > 10000000:
                return self._error_message("Image size is greater than 10MB")

            # check file formats
            if not path.lower().endswith(ALLOWED_EXTENSIONS):
                return self._error_message("Invalid file format")

            upload_url = "https://api.cloudflare.com/client/v4/accounts/{account_id}/images/v1".format(
                account_id=self._account_hash
            )
            header = {
                "Authorization": "Bearer {apiToken}".format(apiToken=self._key),
            }

            # handles file not found
            try:
                file = {
                    "file": open("{path_to_image}".format(path_to_image=path), "rb"),
                }
            except FileNotFoundError:
                return self._error_message("File not found")

            response = requests.post(upload_url, headers=header, files=file)
            return response.json()
        except Exception as e:
            return self._error_message(str(e))

    def delete(self, image_id: str) -> dict:
        """
        Deletes a file from cloudflare's image CDN.

        Response example:
        {
        "errors": [],
        "messages": [],
        "result": {},
        "success": true
        }

        Args:
            image_id (str): The ID of the image to delete.

        Returns:
            dict: A dictionary containing the response from cloudflare's image CDN.
        """
        try:
            upload_url = "https://api.cloudflare.com/client/v4/accounts/{account_id}/images/v1/{image_id}".format(
                account_id=self._account_hash, image_id=image_id
            )
            header = {
                "Authorization": "Bearer {apiToken}".format(apiToken=self._key),
            }
            response = requests.delete(upload_url, headers=header)
            return response.json()
        except Exception as e:
            return self._error_message(str(e))

    def get_image_details(self, image_id: str) -> dict:
        """
        Gets a link to a file from cloudflare's image CDN.
        ["result"]["variants"][0] is the link to the image.

        Response example:
        {
        "errors": [],
        "messages": [],
        "result": {
            "filename": "logo.png",
            "id": "107b9558-dd06-4bbd-5fef-9c2c16bb7900",
            "meta": {
            "key": "value"
            },
            "requireSignedURLs": true,
            "uploaded": "2014-01-02T02:20:00.123Z",
            "variants": [
            "https://imagedelivery.net/MTt4OTd0b0w5aj/107b9558-dd06-4bbd-5fef-9c2c16bb7900/thumbnail",
            "https://imagedelivery.net/MTt4OTd0b0w5aj/107b9558-dd06-4bbd-5fef-9c2c16bb7900/hero",
            "https://imagedelivery.net/MTt4OTd0b0w5aj/107b9558-dd06-4bbd-5fef-9c2c16bb7900/original"
            ]
        },
        "success": true
        }

        Args:
            image_id (str): The ID of the image to get the link for.

        Returns:
            dict: A dictionary containing the response from cloudflare's image CDN.
        """
        try:
            upload_url = "https://api.cloudflare.com/client/v4/accounts/{account_id}/images/v1/{image_id}".format(
                account_id=self._account_hash, image_id=image_id
            )
            header = {
                "Authorization": "Bearer {apiToken}".format(apiToken=self._key),
            }
            response = requests.get(upload_url, headers=header)
            return response.json()
        except Exception as e:
            return self._error_message(str(e))

    def download_original(self, image_id: str) -> str:
        """
        Downloads the original file from cloudflare's image CDN and saves it within a temporary folder.
        Please delete file in temporary folder after use!!! (CDN.empty_temp_folder())

        Args:
            image_id (str): The ID of the image to download.

        Returns:
            str: The path to the downloaded file or an error message that prefixes with: "ERROR_FAIL" followed by the error message.
        """
        try:
            # uuid is used to generate a unique file name
            fileName = (
                str(uuid.uuid4())
                + self.get_image_details(image_id)["result"]["filename"]
            )

            path = TEMP_FOLDER + fileName

            upload_url = "https://api.cloudflare.com/client/v4/accounts/{account_id}/images/v1/{image_id}/blob".format(
                account_id=self._account_hash, image_id=image_id
            )
            header = {
                "Authorization": "Bearer {apiToken}".format(apiToken=self._key),
            }
            blob = requests.get(upload_url, headers=header)
            # print(type(blob.content))

            with open(path, "wb") as bn_fl:
                bn_fl.write(blob.content)
                bn_fl.close()

            return path
        except Exception as e:
            return "ERROR_FAIL: " + str(e)

    # def test(self) -> dict:
    #     # TODO add iterative request to get all images
    #     """
    #     Downloads the original file from cloudflare's image CDN and saves it within a temporary folder.
    #     Please delete file in temporary folder after use!!! (CDN.empty_temp_folder())

    #     Args:
    #         image_id (str): The ID of the image to download.

    #     Returns:
    #         str: The path to the downloaded file or an error message that prefixes with: "ERROR_FAIL" followed by the error message.
    #     """
    #     try:
    #         upload_url = "https://api.cloudflare.com/client/v4/accounts/{account_id}/images/v2".format(
    #             account_id=self._account_hash
    #         )
    #         header = {
    #             "Authorization": "Bearer {apiToken}".format(apiToken=self._key),
    #         }
    #         response = requests.get(upload_url, headers=header)
    #         return response.json()

    #     except Exception as e:
    #         return "ERROR_FAIL: " + str(e)

    def empty_temp_folder(self) -> bool:
        """
        Empties the temporary folder used to store downloaded files.

        Returns:
            bool: True if the folder was emptied successfully, False otherwise.
        """
        try:
            folder = TEMP_FOLDER
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(
                            file_path
                        )  # This will remove a folder and all its contents
                except Exception as e:
                    print("Failed to delete %s. Reason: %s" % (file_path, e))
                    return False
            return True
        except Exception:
            return False

    def check_image(self, file) -> bool:
        """
        Checks if the file is allowed to be uploaded.

        Args: 
            file (FileStorage): The file to check

        Returns:
            bool: True if the file is allowed to be uploaded, False otherwise
        """

        # according to co-pilot, this is a secure way to handle file uploads
        # this uses the werkzeug.utils library
        filename = secure_filename(file.filename)
        if not file:
            flash("No file uploaded", "error")
            return False

        if not self._allowed_file(file.filename):
            flash("File type not allowed", "error")
            return False

        if file.content_length > MAX_FILE_SIZE:
            flash("File size too large", "error")
            return False
        return True

    def _allowed_file(self, filename) -> bool:
        """
        Check if the file is allowed to be uploaded

        Args:
            filename (str): the name of the file

        Returns: 
            bool: True if the file is allowed to be uploaded, False otherwise
        """
        return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    def _error_message(self, message: str) -> dict:
        """
        Returns a dictionary with an error message.

        Args:
            message (str): The error message.

        Returns:
            dict: A dictionary containing the error message.
        """
        return {
            "errors": [message],
            "messages": [],
            "result": {},
            "success": False,
        }


def main():
    """
    The main function used for manually testing the CDN class.
    https://api.cloudflare.com/client/v4/accounts/{account_id}/images/v2
    """

    cdn = CDN()
    # output = cdn.upload(
    #     "./temp/DEBUG_PROFILE_PICTURE_Grace Turner_22769.png")
    # print(output)
    # print(cdn.download_original("57ca5a8c-f909-429d-d4cb-4b00b75f6d00"))
    cdn.empty_temp_folder()
    # print(cdn.test())
    # print(cdn.get_image_details("57ca5a8c-f909-429d-d4cb-4b00b75f6d00"))


if __name__ == "__main__":
    main()


"""
Notes:
https://developers.cloudflare.com/api/operations/cloudflare-images-base-image
https://developers.cloudflare.com/images/upload-images/
"""
