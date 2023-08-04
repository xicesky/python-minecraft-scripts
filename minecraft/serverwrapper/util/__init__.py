
import logging
import os

logger = logging.getLogger(__name__)


def symlink(src, dest_dir, dest_name=None, relative=True, overwrite=False):
    if not os.path.exists(dest_dir):
        raise FileNotFoundError(f"Destination directory {dest_dir} does not exist")
    if not os.path.isdir(dest_dir):
        raise FileNotFoundError(f"Destination {dest_dir} is not a directory")
    if not os.path.exists(src):
        raise FileNotFoundError(f"Source file {src} does not exist")

    dest_name = dest_name or os.path.basename(src)
    link = dest_dir + "/" + dest_name
    if os.path.lexists(link):
        if overwrite:
            logger.debug(f"Removing file {link} to replace with link")
            os.unlink(link)
        else:
            raise FileExistsError(f"Target file {link} already exists")

    link_destination = src
    if relative:
        link_destination = os.path.relpath(src, dest_dir)
    else:
        link_destination = os.path.abspath(src)

    logger.info(f"Creating symlink {link} to {link_destination}")
    os.symlink(link_destination, link)
