"""
Core utilities.

| Copyright 2017-2020, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""
import importlib
import logging
import resource
import sys
import types

import packaging.version

import eta.core.utils as etau


logger = logging.getLogger(__name__)


class LazyImporter(types.ModuleType):
    """Class for lazily importing a module, allowing it to be imported only
    when it is actually used in the code.

    Example usage::

        # Lazy version of `import tensorflow as tf`
        tf = LazyImporter("tensorflow", "tf", globals())

    Args:
        module_name: the name of the module to import
        local_name: the desired local name of the module in the caller's
            namespace
        parent_module_globals: the caller's ``globals()``
        load_callback (None): an optional callback function to call before
            loading the module
    """

    def __init__(
        self,
        module_name,
        local_name,
        parent_module_globals,
        load_callback=None,
    ):
        super(LazyImporter, self).__init__(module_name)
        self._local_name = local_name
        self._parent_module_globals = parent_module_globals
        self._load_callback = load_callback

    def _load(self):
        # Execute load callback, if provided
        if self._load_callback is not None:
            self._load_callback()

        # Import the target module and insert it into the parent's namespace
        module = importlib.import_module(self.__name__)
        self._parent_module_globals[self._local_name] = module

        #
        # Update this object's dict so that if someone keeps a reference to the
        # LazyImporter, lookups are efficient (__getattr__ is only called on
        # lookups that fail)
        #
        self.__dict__.update(module.__dict__)
        return module

    def __getattr__(self, item):
        module = self._load()
        return getattr(module, item)

    def __dir__(self):
        module = self._load()
        return dir(module)


def ensure_tf():
    """Verifies that TensorFlow is installed on the host machine.

    Raises:
        ImportError: if ``tensorflow`` could not be imported
    """
    _ensure_package("tensorflow")


def ensure_tfds():
    """Verifies that the ``tensorflow_datasets`` package is installed on the
    host machine.

    Raises:
        ImportError: if ``tensorflow_datasets`` could not be imported
    """
    _ensure_package("tensorflow", min_version="1.15")
    _ensure_package("tensorflow_datasets")


def ensure_torch():
    """Verifies that PyTorch is installed on the host machine.

    Raises:
        ImportError: if ``torch`` or ``torchvision`` could not be imported
    """
    _ensure_package("torch")
    _ensure_package("torchvision")


def _ensure_package(package_name, min_version=None):
    has_min_ver = min_version is not None

    if has_min_ver:
        min_version = packaging.version.parse(min_version)

    try:
        pkg = importlib.import_module(package_name)
    except ImportError as e:
        if has_min_ver:
            pkg_str = "%s>=%s" % (package_name, min_version)
        else:
            pkg_str = package_name

        raise ImportError(
            "The requested operation requires that '%s' is installed on your "
            "machine" % pkg_str
        ) from e

    if has_min_ver:
        pkg_version = packaging.version.parse(pkg.__version__)
        if pkg_version < min_version:
            raise ImportError(
                "The requested operation requires that '%s>=%s' is installed "
                "on your machine; found '%s==%s'"
                % (package_name, min_version, package_name, pkg_version)
            )


def parse_serializable(obj, cls):
    """Parses the given object as an instance of the given
    ``eta.core.serial.Serializable`` class.

    Args:
        obj: an instance of ``cls``, or a serialized string or dictionary
            representation of one
        cls: a ``eta.core.serial.Serializable`` class

    Returns:
        an instance of ``cls``
    """
    if isinstance(obj, cls):
        return obj

    if etau.is_str(obj):
        return cls.from_str(obj)

    if isinstance(obj, dict):
        return cls.from_dict(obj)

    raise ValueError(
        "Unable to load '%s' as an instance of '%s'"
        % (obj, etau.get_class_name(cls))
    )


class ResourceLimit(object):
    """Context manager that allows for a temporary change to a resource limit
    exposed by the `resource` package.

    Example::

        import resource

        with ResourceLimit(resource.RLIMIT_NOFILE, soft=4096):
            # temporarily do things with up to 4096 open files

    Args:
        limit: the resource to limit. See the documentation of the
            `resource` module for supported values
        soft: a new soft limit to apply, which cannot exceed the hard limit
        hard: a new hard limit to apply, which cannot exceed the current
            hard limit
        warn_on_failure: whether to issue a warning rather than an error
            if the resource limit change is not successful
    """

    def __init__(self, limit, soft=None, hard=None, warn_on_failure=False):
        self._limit = limit
        self._soft = soft
        self._hard = hard
        self._soft_orig = None
        self._hard_orig = None
        self._warn_on_failure = warn_on_failure

    def __enter__(self):
        self._soft_orig, self._hard_orig = resource.getrlimit(self._limit)
        soft = self._soft or self._soft_orig
        hard = self._hard or self._hard_orig
        self._set_resource_limit(soft, hard)
        return self

    def __exit__(self, *args):
        self._set_resource_limit(self._soft_orig, self._hard_orig)

    def _set_resource_limit(self, soft, hard):
        try:
            resource.setrlimit(self._limit, (soft, hard))
        except ValueError as e:
            if self._warn_on_failure:
                logger.warning(e)
            else:
                raise


def compute_filehash(filepath):
    """Computes the file hash of the given file.

    Args:
        filepath: the path to the file

    Returns:
        the file hash
    """
    with open(filepath, "rb") as f:
        return hash(f.read())
