import os.path

def samefile(path1, path2):
    try:
        return os.path.samefile(path1, path2)
    except FileNotFoundError:
        return False

class FilterModule(object):
    """Custom filters are loaded by FilterModule objects"""

    def filters(self):
        """FilterModule objects return a dict mapping filter names to
        filter functions."""
        return {
            "abspath": os.path.abspath,
            "normpath": os.path.normpath,
            "samefile": samefile,
            "isfile": os.path.isfile
        }
