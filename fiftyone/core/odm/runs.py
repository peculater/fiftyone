"""
Dataset run documents.

| Copyright 2017-2022, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""
from mongoengine import (
    DictField,
    ListField,
    StringField,
    DateTimeField,
    FileField,
)

from .document import Document


class RunDocument(Document):
    """Backing document for dataset runs."""

    meta = {"collection": "runs"}

    key = StringField()
    version = StringField()
    timestamp = DateTimeField()
    config = DictField()
    view_stages = ListField(StringField())
    results = FileField()
