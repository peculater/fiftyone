"""
Dataset sample fields.

| Copyright 2017-2021, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""
from bson.binary import Binary
import mongoengine.fields
import numpy as np
import six

import eta.core.image as etai
import eta.core.utils as etau

import fiftyone.core.utils as fou
import fiftyone.core.frame_utils as fofu


def parse_field_str(field_str):
    """Parses the string representation of a :class:`Field` generated by
    ``str(field)`` into components that can be passed to
    :meth:`fiftyone.core.dataset.Dataset.add_sample_field`.

    Returns:
        a tuple of

        -   ftype: the :class:`fiftyone.core.fields.Field` class
        -   embedded_doc_type: the
                :class:`fiftyone.core.odm.BaseEmbeddedDocument` type of the
                field, or ``None``
        -   subfield: the :class:`fiftyone.core.fields.Field` class of the
                subfield, or ``None``
    """
    chunks = field_str.strip().split("(", 1)
    ftype = etau.get_class(chunks[0])
    embedded_doc_type = None
    subfield = None
    if len(chunks) > 1:
        param = etau.get_class(chunks[1][:-1])  # remove trailing ")"
        if issubclass(ftype, EmbeddedDocumentField):
            embedded_doc_type = param
        elif issubclass(ftype, (ListField, DictField)):
            subfield = param
        else:
            raise ValueError("Failed to parse field string '%s'" % field_str)

    return ftype, embedded_doc_type, subfield


class Field(mongoengine.fields.BaseField):
    """Base class for :class:`fiftyone.core.sample.Sample` fields."""

    def __str__(self):
        return etau.get_class_name(self)


class ObjectIdField(mongoengine.ObjectIdField, Field):
    """An Object ID field."""

    pass


class UUIDField(mongoengine.UUIDField, Field):
    """A UUID field."""

    pass


class BooleanField(mongoengine.BooleanField, Field):
    """A boolean field."""

    pass


class IntField(mongoengine.IntField, Field):
    """A 32 bit integer field."""

    pass


class FrameNumberField(IntField):
    """A video frame number field."""

    def validate(self, value):
        try:
            fofu.validate_frame_number(value)
        except fofu.FrameError as e:
            self.error(str(e))


class FloatField(mongoengine.FloatField, Field):
    """A floating point number field."""

    def validate(self, value):
        try:
            value = float(value)
        except OverflowError:
            self.error("The value is too large to be converted to float")
        except (TypeError, ValueError):
            self.error("%s could not be converted to float" % value)

        if self.min_value is not None and value < self.min_value:
            self.error("Float value is too small")

        if self.max_value is not None and value > self.max_value:
            self.error("Float value is too large")


class StringField(mongoengine.StringField, Field):
    """A unicode string field."""

    pass


class ListField(mongoengine.ListField, Field):
    """A list field that wraps a standard :class:`Field`, allowing multiple
    instances of the field to be stored as a list in the database.

    If this field is not set, its default value is ``[]``.

    Args:
        field (None): an optional :class:`Field` instance describing the
            type of the list elements
    """

    def __init__(self, field=None, **kwargs):
        if field is not None:
            if not isinstance(field, Field):
                raise ValueError(
                    "Invalid field type '%s'; must be a subclass of %s"
                    % (type(field), Field)
                )

        super().__init__(field=field, **kwargs)

    def __str__(self):
        if self.field is not None:
            return "%s(%s)" % (
                etau.get_class_name(self),
                etau.get_class_name(self.field),
            )

        return etau.get_class_name(self)


class KeypointsField(ListField):
    """A list of ``(x, y)`` coordinate pairs.

    If this field is not set, its default value is ``[]``.
    """

    def __init__(self, **kwargs):
        super().__init__(field=None, **kwargs)

    def __str__(self):
        return etau.get_class_name(self)

    def validate(self, value):
        # Only validate value[0], for efficiency
        if not isinstance(value, (list, tuple)) or (
            value
            and (not isinstance(value[0], (list, tuple)) or len(value[0]) != 2)
        ):
            self.error("Keypoints fields must contain a list of (x, y) pairs")


class PolylinePointsField(ListField):
    """A list of lists of ``(x, y)`` coordinate pairs.

    If this field is not set, its default value is ``[]``.
    """

    def __init__(self, **kwargs):
        super().__init__(field=None, **kwargs)

    def __str__(self):
        return etau.get_class_name(self)

    def validate(self, value):
        # Only validate value[0] and value[0][0], for efficiency
        if (
            not isinstance(value, (list, tuple))
            or (value and not isinstance(value[0], (list, tuple)))
            or (
                value
                and value[0]
                and (
                    not isinstance(value[0][0], (list, tuple))
                    or len(value[0][0]) != 2
                )
            )
        ):
            self.error(
                "Polyline points fields must contain a list of lists of "
                "(x, y) pairs"
            )


class GeoPointField(mongoengine.fields.PointField, Field):
    """A GeoJSON field storing a longitude and latitude coordinate point.

    The data is stored as ``[longitude, latitude]``.
    """

    pass


class GeoLineStringField(mongoengine.fields.LineStringField, Field):
    """A GeoJSON field storing a line of longitude and latitude coordinates.

    The data is stored as follow::

        [[lon1, lat1], [lon2, lat2], ...]
    """

    pass


class GeoPolygonField(mongoengine.fields.PolygonField, Field):
    """A GeoJSON field storing a polygon of longitude and latitude coordinates.

    The data is stored as follows::

        [
            [[lon1, lat1], [lon2, lat2], ...],
            [[lon1, lat1], [lon2, lat2], ...],
            ...
        ]

    where the first element describes the boundary of the polygon and any
    remaining entries describe holes.
    """

    pass


class GeoMultiPointField(mongoengine.fields.MultiPointField, Field):
    """A GeoJSON field storing a list of points.

    The data is stored as follows::

        [[lon1, lat1], [lon2, lat2], ...]
    """

    pass


class GeoMultiLineStringField(mongoengine.fields.MultiLineStringField, Field):
    """A GeoJSON field storing a list of lines.

    The data is stored as follows::

        [
            [[lon1, lat1], [lon2, lat2], ...],
            [[lon1, lat1], [lon2, lat2], ...],
            ...
        ]
    """

    pass


class GeoMultiPolygonField(mongoengine.fields.MultiPolygonField, Field):
    """A GeoJSON field storing a list of polygons.

    The data is stored as follows::

        [
            [
                [[lon1, lat1], [lon2, lat2], ...],
                [[lon1, lat1], [lon2, lat2], ...],
                ...
            ],
            [
                [[lon1, lat1], [lon2, lat2], ...],
                [[lon1, lat1], [lon2, lat2], ...],
                ...
            ],
            ...
        ]
    """

    pass


class DictField(mongoengine.fields.DictField, Field):
    """A dictionary field that wraps a standard Python dictionary.

    If this field is not set, its default value is ``{}``.

    Args:
        field (None): an optional :class:`Field` instance describing the type
            of the values in the dict
    """

    def __init__(self, field=None, **kwargs):
        if field is not None:
            if not isinstance(field, Field):
                raise ValueError(
                    "Invalid field type '%s'; must be a subclass of %s"
                    % (type(field), Field)
                )

        super().__init__(field=field, **kwargs)

    def __str__(self):
        if self.field is not None:
            return "%s(%s)" % (
                etau.get_class_name(self),
                etau.get_class_name(self.field),
            )

        return etau.get_class_name(self)


class VectorField(mongoengine.fields.BinaryField, Field):
    """A one-dimensional array field.

    :class:`VectorField` instances accept numeric lists, tuples, and 1D numpy
    array values. The underlying data is serialized and stored in the database
    as zlib-compressed bytes generated by ``numpy.save`` and always retrieved
    as a numpy array.
    """

    def to_mongo(self, value):
        if value is None:
            return None

        bytes = fou.serialize_numpy_array(value)
        return super().to_mongo(bytes)

    def to_python(self, value):
        if value is None or isinstance(value, np.ndarray):
            return value

        return fou.deserialize_numpy_array(value)

    def validate(self, value):
        if isinstance(value, np.ndarray):
            if value.ndim > 1:
                self.error("Only 1D arrays may be used in a vector field")
        elif not isinstance(value, (list, tuple, Binary)):
            self.error(
                "Only numpy arrays, lists, and tuples may be used in a "
                "vector field"
            )


class ArrayField(mongoengine.fields.BinaryField, Field):
    """An n-dimensional array field.

    :class:`ArrayField` instances accept numpy array values. The underlying
    data is serialized and stored in the database as zlib-compressed bytes
    generated by ``numpy.save`` and always retrieved as a numpy array.
    """

    def to_mongo(self, value):
        if value is None:
            return None

        bytes = fou.serialize_numpy_array(value)
        return super().to_mongo(bytes)

    def to_python(self, value):
        if value is None or isinstance(value, np.ndarray):
            return value

        return fou.deserialize_numpy_array(value)

    def validate(self, value):
        if not isinstance(value, (np.ndarray, Binary)):
            self.error("Only numpy arrays may be used in an array field")


class EmbeddedDocumentField(mongoengine.EmbeddedDocumentField, Field):
    """A field that stores instances of a given type of
    :class:`fiftyone.core.odm.BaseEmbeddedDocument` object.

    Args:
        document_type: the :class:`fiftyone.core.odm.BaseEmbeddedDocument` type
            stored in this field
    """

    def __init__(self, document_type, **kwargs):
        #
        # @todo resolve circular import errors in `fiftyone.core.odm.sample`
        # so that this validation can occur here
        #
        # import fiftyone.core.odm as foo
        #
        # if not issubclass(document_type, foo.BaseEmbeddedDocument):
        #     raise ValueError(
        #         "Invalid document type %s; must be a subclass of %s"
        #         % (document_type, foo.BaseEmbeddedDocument)
        #     )
        #

        super().__init__(document_type, **kwargs)

    def __str__(self):
        return "%s(%s)" % (
            etau.get_class_name(self),
            etau.get_class_name(self.document_type),
        )


_ARRAY_FIELDS = (VectorField, ArrayField)
