"""
Clips views.

| Copyright 2017-2022, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""
from copy import deepcopy
from collections import defaultdict

from bson import ObjectId

import eta.core.utils as etau

import fiftyone.core.dataset as fod
import fiftyone.core.expressions as foe
from fiftyone.core.expressions import ViewField as F
import fiftyone.core.fields as fof
import fiftyone.core.labels as fol
import fiftyone.core.media as fom
import fiftyone.core.sample as fos
import fiftyone.core.validation as fova
import fiftyone.core.view as fov


class ClipView(fos.SampleView):
    """A clip in a :class:`ClipsView`.

    :class:`ClipView` instances should not be created manually; they are
    generated by iterating over :class:`ClipsView` instances.

    Args:
        doc: a :class:`fiftyone.core.odm.DatasetSampleDocument`
        view: the :class:`ClipsView` that the frame belongs to
        selected_fields (None): a set of field names that this view is
            restricted to
        excluded_fields (None): a set of field names that are excluded from
            this view
        filtered_fields (None): a set of field names of list fields that are
            filtered in this view
    """

    @property
    def _sample_id(self):
        return ObjectId(self._doc.sample_id)

    def save(self):
        """Saves the clip to the database."""
        super().save()
        self._view._sync_source_sample(self)


class ClipsView(fov.DatasetView):
    """A :class:`fiftyone.core.view.DatasetView` of clips from a video
    :class:`fiftyone.core.dataset.Dataset`.

    Clips views contain an ordered collection of clips, each of which
    corresponds to a range of frame numbers from the source collection.

    Clips retrieved from clips views are returned as :class:`ClipView` objects.

    Args:
        source_collection: the
            :class:`fiftyone.core.collections.SampleCollection` from which this
            view was created
        clips_stage: the :class:`fiftyone.core.stages.ToClips` stage that
            defines how the clips were created
        clips_dataset: the :class:`fiftyone.core.dataset.Dataset` that serves
            the clips in this view
    """

    def __init__(
        self, source_collection, clips_stage, clips_dataset, _stages=None
    ):
        if _stages is None:
            _stages = []

        self._classification_field = self._get_temporal_detection_field(
            source_collection, clips_stage
        )
        self._source_collection = source_collection
        self._clips_stage = clips_stage
        self._clips_dataset = clips_dataset
        self.__stages = _stages

    def __copy__(self):
        return self.__class__(
            self._source_collection,
            deepcopy(self._clips_stage),
            self._clips_dataset,
            _stages=deepcopy(self.__stages),
        )

    @staticmethod
    def _get_temporal_detection_field(source_collection, clips_stage):
        try:
            fova.validate_collection_label_fields(
                source_collection,
                clips_stage.field_or_expr,
                (fol.TemporalDetection, fol.TemporalDetections),
            )
            return clips_stage.field_or_expr
        except:
            return None

    @property
    def _base_view(self):
        return self.__class__(
            self._source_collection,
            self._clips_stage,
            self._clips_dataset,
        )

    @property
    def _dataset(self):
        return self._clips_dataset

    @property
    def _root_dataset(self):
        return self._source_collection._root_dataset

    @property
    def _sample_cls(self):
        return ClipView

    @property
    def _stages(self):
        return self.__stages

    @property
    def _all_stages(self):
        return (
            self._source_collection.view()._all_stages
            + [self._clips_stage]
            + self.__stages
        )

    @property
    def _element_str(self):
        return "clip"

    @property
    def _elements_str(self):
        return "clips"

    @property
    def name(self):
        return self.dataset_name + "-clips"

    def _get_default_sample_fields(
        self, include_private=False, use_db_fields=False
    ):
        fields = super()._get_default_sample_fields(
            include_private=include_private, use_db_fields=use_db_fields
        )

        if use_db_fields:
            return fields + ("_sample_id", "support")

        return fields + ("sample_id", "support")

    def _get_default_indexes(self, frames=False):
        if frames:
            return super()._get_default_indexes(frames=frames)

        return ["id", "filepath", "sample_id"]

    def set_values(self, field_name, *args, **kwargs):
        # The `set_values()` operation could change the contents of this view,
        # so we first record the sample IDs that need to be synced
        if self._stages:
            ids = self.values("id")
        else:
            ids = None

        super().set_values(field_name, *args, **kwargs)

        field = field_name.split(".", 1)[0]
        self._sync_source(fields=[field], ids=ids)

    def save(self, fields=None):
        """Saves the clips in this view to the underlying dataset.

        .. note::

            This method is not a :class:`fiftyone.core.stages.ViewStage`;
            it immediately writes the requested changes to the underlying
            dataset.

        .. warning::

            This will permanently delete any omitted or filtered contents from
            the frames of the underlying dataset.

        Args:
            fields (None): an optional field or list of fields to save. If
                specified, only these fields are overwritten
        """
        if etau.is_str(fields):
            fields = [fields]

        self._sync_source(fields=fields)

        super().save(fields=fields)

    def keep(self):
        """Deletes all clips that are **not** in this view from the underlying
        dataset.

        .. note::

            This method is not a :class:`fiftyone.core.stages.ViewStage`;
            it immediately writes the requested changes to the underlying
            dataset.
        """
        self._sync_source(update=False, delete=True)

        super().keep()

    def keep_fields(self):
        """Deletes any frame fields that have been excluded in this view from
        the frames of the underlying dataset.

        .. note::

            This method is not a :class:`fiftyone.core.stages.ViewStage`;
            it immediately writes the requested changes to the underlying
            dataset.
        """
        self._sync_source_keep_fields()

        super().keep_fields()

    def reload(self):
        """Reloads this view from the source collection in the database.

        Note that :class:`ClipView` instances are not singletons, so any
        in-memory clips extracted from this view will not be updated by calling
        this method.
        """
        self._source_collection.reload()

        #
        # Regenerate the clips dataset
        #
        # This assumes that calling `load_view()` when the current clips
        # dataset has been deleted will cause a new one to be generated
        #

        self._clips_dataset.delete()
        _view = self._clips_stage.load_view(self._source_collection)
        self._clips_dataset = _view._clips_dataset

    def _sync_source_sample(self, sample):
        if not self._classification_field:
            return

        # Sync label + support to underlying TemporalDetection

        field = self._classification_field

        classification = sample[field]
        if classification is not None:
            doc = classification.to_dict()
            doc["_cls"] = "TemporalDetection"
            doc["support"] = sample.support
        else:
            doc = None

        self._source_collection._set_labels(field, [sample.sample_id], [doc])

    def _sync_source(self, fields=None, ids=None, update=True, delete=False):
        if not self._classification_field:
            return

        field = self._classification_field

        if fields is not None and field not in fields:
            return

        # Sync label + support to underlying TemporalDetection

        if ids is not None:
            sync_view = self._clips_dataset.select(ids)
        else:
            sync_view = self

        update_ids = []
        update_docs = []
        del_ids = set()
        for label_id, sample_id, support, doc in zip(
            *sync_view.values(["id", "sample_id", "support", field], _raw=True)
        ):
            if doc:
                doc["support"] = support
                doc["_cls"] = "TemporalDetection"
                update_ids.append(sample_id)
                update_docs.append(doc)
            else:
                del_ids.add(label_id)

        if delete:
            observed_ids = set(update_ids)
            for label_id, sample_id in zip(
                *self._clips_dataset.values(["id", "sample_id"])
            ):
                if sample_id not in observed_ids:
                    del_ids.add(label_id)

        if update:
            self._source_collection._set_labels(field, update_ids, update_docs)

        if del_ids:
            # @todo can we optimize this? we know exactly which samples each
            # label to be deleted came from
            self._source_collection._delete_labels(del_ids, fields=[field])

    def _sync_source_keep_fields(self):
        # If the source TemporalDetection field is excluded, delete it from
        # this collection and the source collection
        cls_field = self._classification_field
        if cls_field and cls_field not in self.get_field_schema():
            self._source_collection.exclude_fields(cls_field).keep_fields()

        # Delete any excluded frame fields from this collection and the source
        # collection
        schema = self.get_frame_field_schema()
        src_schema = self._source_collection.get_frame_field_schema()

        del_fields = set(src_schema.keys()) - set(schema.keys())
        if del_fields:
            prefix = self._source_collection._FRAMES_PREFIX
            _del_fields = [prefix + f for f in del_fields]
            self._source_collection.exclude_fields(_del_fields).keep_fields()


def make_clips_dataset(
    sample_collection,
    field_or_expr,
    other_fields=None,
    tol=0,
    min_len=0,
    trajectories=False,
):
    """Creates a dataset that contains one sample per clip defined by the
    given field or expression in the collection.

    The returned dataset will contain:

    -   A ``sample_id`` field that records the sample ID from which each clip
        was taken
    -   A ``support`` field that records the ``[first, last]`` frame support of
        each clip
    -   All frame-level information from the underlying dataset of the input
        collection

    In addition, sample-level fields will be added for certain clipping
    strategies:

    -   When ``field_or_expr`` is a temporal detection(s) field, the field
        will be converted to a :class:`fiftyone.core.labels.Classification`
        field
    -   When ``trajectories`` is True, a sample-level label field will be added
        recording the ``label`` and ``index`` of each trajectory

    .. note::

        The returned dataset will directly use the frame collection of the
        input dataset.

    Args:
        sample_collection: a
            :class:`fiftyone.core.collections.SampleCollection`
        field_or_expr: can be any of the following:

            -   a :class:`fiftyone.core.labels.TemporalDetection`,
                :class:`fiftyone.core.labels.TemporalDetections`,
                :class:`fiftyone.core.fields.FrameSupportField`, or list of
                :class:`fiftyone.core.fields.FrameSupportField` field
            -   a frame-level label list field of any of the following types:

                -   :class:`fiftyone.core.labels.Classifications`
                -   :class:`fiftyone.core.labels.Detections`
                -   :class:`fiftyone.core.labels.Polylines`
                -   :class:`fiftyone.core.labels.Keypoints`
            -   a :class:`fiftyone.core.expressions.ViewExpression` that
                returns a boolean to apply to each frame of the input
                collection to determine if the frame should be clipped
            -   a list of ``[(first1, last1), (first2, last2), ...]`` lists
                defining the frame numbers of the clips to extract from each
                sample
        other_fields (None): controls whether sample fields other than the
            default sample fields are included. Can be any of the following:

            -   a field or list of fields to include
            -   ``True`` to include all other fields
            -   ``None``/``False`` to include no other fields
        tol (0): the maximum number of false frames that can be overlooked when
            generating clips. Only applicable when ``field_or_expr`` is a
            frame-level list field or expression
        min_len (0): the minimum allowable length of a clip, in frames. Only
            applicable when ``field_or_expr`` is a frame-level list field or an
            expression
        trajectories (False): whether to create clips for each unique object
            trajectory defined by their ``(label, index)``. Only applicable
            when ``field_or_expr`` is a frame-level field

    Returns:
        a :class:`fiftyone.core.dataset.Dataset`
    """
    fova.validate_video_collection(sample_collection)

    if etau.is_str(other_fields):
        other_fields = [other_fields]

    if etau.is_str(field_or_expr):
        if sample_collection._is_frame_field(field_or_expr):
            if trajectories:
                clips_type = "trajectories"
            else:
                clips_type = "expression"
        else:
            if _is_frame_support_field(sample_collection, field_or_expr):
                clips_type = "support"
            else:
                clips_type = "detections"
    elif isinstance(field_or_expr, (foe.ViewExpression, dict)):
        clips_type = "expression"
    else:
        clips_type = "manual"

    dataset = fod.Dataset(_clips=True, _src_collection=sample_collection)
    dataset._doc.app_sidebar_groups = (
        sample_collection._dataset._doc.app_sidebar_groups
    )
    dataset.media_type = fom.VIDEO
    dataset.add_sample_field(
        "sample_id", fof.ObjectIdField, db_field="_sample_id"
    )
    dataset.create_index("sample_id")
    dataset.add_sample_field("support", fof.FrameSupportField)

    if clips_type == "detections":
        dataset.add_sample_field(
            field_or_expr,
            fof.EmbeddedDocumentField,
            embedded_doc_type=fol.Classification,
        )

    if clips_type == "trajectories":
        field_or_expr, _ = sample_collection._handle_frame_field(field_or_expr)
        dataset.add_sample_field(
            field_or_expr,
            fof.EmbeddedDocumentField,
            embedded_doc_type=fol.Label,
        )

    if other_fields:
        src_schema = sample_collection.get_field_schema()
        curr_schema = dataset.get_field_schema()

        if other_fields == True:
            other_fields = [f for f in src_schema if f not in curr_schema]

        add_fields = [f for f in other_fields if f not in curr_schema]
        dataset._sample_doc_cls.merge_field_schema(
            [], {k: v for k, v in src_schema.items() if k in add_fields}
        )

    _make_pretty_summary(dataset)

    if clips_type == "support":
        _write_support_clips(
            dataset,
            sample_collection,
            field_or_expr,
            other_fields=other_fields,
        )
    elif clips_type == "detections":
        _write_temporal_detection_clips(
            dataset,
            sample_collection,
            field_or_expr,
            other_fields=other_fields,
        )
    elif clips_type == "trajectories":
        _write_trajectories(
            dataset,
            sample_collection,
            field_or_expr,
            other_fields=other_fields,
        )
    elif clips_type == "expression":
        _write_expr_clips(
            dataset,
            sample_collection,
            field_or_expr,
            other_fields=other_fields,
            tol=tol,
            min_len=min_len,
        )
    else:
        _write_manual_clips(
            dataset,
            sample_collection,
            field_or_expr,
            other_fields=other_fields,
        )

    return dataset


def _is_frame_support_field(sample_collection, field_path):
    field = sample_collection.get_field(field_path)
    return isinstance(field, fof.FrameSupportField) or (
        isinstance(field, fof.ListField)
        and isinstance(field.field, fof.FrameSupportField)
    )


def _make_pretty_summary(dataset):
    set_fields = ["id", "sample_id", "filepath", "support"]
    all_fields = dataset._sample_doc_cls._fields_ordered
    pretty_fields = set_fields + [f for f in all_fields if f not in set_fields]
    dataset._sample_doc_cls._fields_ordered = tuple(pretty_fields)


def _write_support_clips(
    dataset, src_collection, field_path, other_fields=None
):
    field = src_collection.get_field(field_path)
    is_list = isinstance(field, fof.ListField) and not isinstance(
        field, fof.FrameSupportField
    )

    src_dataset = src_collection._dataset
    id_field = "_id" if not src_dataset._is_clips else "_sample_id"

    project = {
        "_id": False,
        "_sample_id": "$" + id_field,
        "_media_type": True,
        "_rand": True,
        "filepath": True,
        "metadata": True,
        "tags": True,
        "support": "$" + field.name,
    }

    if other_fields:
        project.update({f: True for f in other_fields})

    pipeline = src_collection._pipeline()
    pipeline.append({"$project": project})

    if is_list:
        pipeline.extend(
            [{"$unwind": "$support"}, {"$set": {"_rand": {"$rand": {}}}}]
        )

    pipeline.append({"$out": dataset._sample_collection_name})

    src_dataset._aggregate(pipeline=pipeline)


def _write_temporal_detection_clips(
    dataset, src_collection, field, other_fields=None
):
    src_dataset = src_collection._dataset
    label_type = src_collection._get_label_field_type(field)

    supported_types = (fol.TemporalDetection, fol.TemporalDetections)
    if label_type not in supported_types:
        raise ValueError(
            "Field '%s' must be a %s type; found %s"
            % (field, supported_types, label_type)
        )

    id_field = "_id" if not src_dataset._is_clips else "_sample_id"

    project = {
        "_id": False,
        "_sample_id": "$" + id_field,
        "_media_type": True,
        "_rand": True,
        "filepath": True,
        "metadata": True,
        "tags": True,
        field: True,
    }

    if other_fields:
        project.update({f: True for f in other_fields})

    pipeline = src_collection._pipeline()

    pipeline.append({"$project": project})

    if label_type is fol.TemporalDetections:
        list_path = field + "." + label_type._LABEL_LIST_FIELD
        pipeline.extend(
            [{"$unwind": "$" + list_path}, {"$set": {field: "$" + list_path}}]
        )

    support_path = field + ".support"
    pipeline.extend(
        [
            {
                "$set": {
                    "_id": "$" + field + "._id",
                    "support": "$" + support_path,
                    field + "._cls": "Classification",
                    "_rand": {"$rand": {}},
                }
            },
            {"$unset": support_path},
            {"$out": dataset._sample_collection_name},
        ]
    )

    src_dataset._aggregate(pipeline=pipeline)


def _write_trajectories(dataset, src_collection, field, other_fields=None):
    path = src_collection._FRAMES_PREFIX + field
    label_type = src_collection._get_label_field_type(path)

    supported_types = (fol.Detections, fol.Polylines, fol.Keypoints)
    if label_type not in supported_types:
        raise ValueError(
            "Frame field '%s' must be a %s type; found %s"
            % (field, supported_types, label_type)
        )

    src_dataset = src_collection._dataset
    _tmp_field = "_" + field

    trajs = _get_trajectories(src_collection, field)
    src_collection.set_values(
        _tmp_field,
        trajs,
        expand_schema=False,
        _allow_missing=True,
    )

    src_collection = fod._always_select_field(src_collection, _tmp_field)

    id_field = "_id" if not src_dataset._is_clips else "_sample_id"

    project = {
        "_id": False,
        "_sample_id": "$" + id_field,
        _tmp_field: True,
        "_media_type": True,
        "filepath": True,
        "metadata": True,
        "tags": True,
        field: True,
    }

    if other_fields:
        project.update({f: True for f in other_fields})

    pipeline = src_collection._pipeline()

    pipeline.extend(
        [
            {"$project": project},
            {"$unwind": "$" + _tmp_field},
            {
                "$set": {
                    "support": {"$slice": ["$" + _tmp_field, 2, 2]},
                    field: {
                        "_cls": "Label",
                        "label": {"$arrayElemAt": ["$" + _tmp_field, 0]},
                        "index": {"$arrayElemAt": ["$" + _tmp_field, 1]},
                    },
                    "_rand": {"$rand": {}},
                },
            },
            {"$unset": _tmp_field},
            {"$out": dataset._sample_collection_name},
        ]
    )

    src_dataset._aggregate(pipeline=pipeline)

    cleanup_op = {"$unset": {_tmp_field: ""}}
    src_dataset._sample_collection.update_many({}, cleanup_op)


def _write_expr_clips(
    dataset, src_collection, expr, other_fields=None, tol=0, min_len=0
):
    if etau.is_str(expr):
        _, path = src_collection._get_label_field_path(expr)
        leaf, _ = src_collection._handle_frame_field(path)
        expr = F(leaf).length() > 0

    if isinstance(expr, dict):
        expr = foe.ViewExpression(expr)

    frame_numbers, bools = src_collection.values(
        ["frames.frame_number", F("frames").map(expr)]
    )

    clips = [
        _to_rle(fns, bs, tol=tol, min_len=min_len)
        for fns, bs in zip(frame_numbers, bools)
    ]

    _write_manual_clips(
        dataset, src_collection, clips, other_fields=other_fields
    )


def _write_manual_clips(dataset, src_collection, clips, other_fields=None):
    src_dataset = src_collection._dataset
    _tmp_field = "_support"

    src_collection.set_values(
        _tmp_field,
        clips,
        expand_schema=False,
        _allow_missing=True,
    )

    src_collection = fod._always_select_field(src_collection, _tmp_field)

    id_field = "_id" if not src_dataset._is_clips else "_sample_id"

    project = {
        "_id": False,
        "_sample_id": "$" + id_field,
        "_media_type": True,
        "filepath": True,
        "support": "$" + _tmp_field,
        "metadata": True,
        "tags": True,
    }

    if other_fields:
        project.update({f: True for f in other_fields})

    pipeline = src_collection._pipeline()

    pipeline.extend(
        [
            {"$project": project},
            {"$unwind": "$support"},
            {"$set": {"_rand": {"$rand": {}}}},
            {"$out": dataset._sample_collection_name},
        ]
    )

    src_dataset._aggregate(pipeline=pipeline)

    cleanup_op = {"$unset": {_tmp_field: ""}}
    src_dataset._sample_collection.update_many({}, cleanup_op)


def _get_trajectories(sample_collection, frame_field):
    path = sample_collection._FRAMES_PREFIX + frame_field
    label_type = sample_collection._get_label_field_type(path)

    if not issubclass(label_type, fol._LABEL_LIST_FIELDS):
        raise ValueError(
            "Frame field '%s' has type %s, but trajectories can only be "
            "extracted for label list fields %s"
            % (
                frame_field,
                label_type,
                fol._LABEL_LIST_FIELDS,
            )
        )

    fn_expr = F("frames").map(F("frame_number"))
    uuid_expr = F("frames").map(
        F(frame_field + "." + label_type._LABEL_LIST_FIELD).map(
            F("label").concat(
                ".", (F("index") != None).if_else(F("index").to_string(), "")
            )
        )
    )

    fns, all_uuids = sample_collection.values([fn_expr, uuid_expr])

    trajs = []
    for sample_fns, sample_uuids in zip(fns, all_uuids):
        if not sample_uuids:
            trajs.append(None)
            continue

        obs = defaultdict(_Bounds)
        for fn, frame_uuids in zip(sample_fns, sample_uuids):
            if not frame_uuids:
                continue

            for uuid in frame_uuids:
                label, index = uuid.rsplit(".", 1)
                if index:
                    index = int(index)
                    obs[(label, index)].add(fn)

        clips = []
        for (label, index), bounds in obs.items():
            clips.append((label, index, bounds.min, bounds.max))

        trajs.append(clips)

    return trajs


class _Bounds(object):
    def __init__(self):
        self.min = None
        self.max = None

    def add(self, value):
        if self.min is None:
            self.min = value
            self.max = value
        else:
            self.min = min(self.min, value)
            self.max = max(self.max, value)


def _to_rle(frame_numbers, bools, tol=0, min_len=0):
    if not frame_numbers:
        return None

    ranges = []
    start = None
    last = None
    for fn, b in zip(frame_numbers, bools):
        if start is not None and fn - last > tol + int(b):
            ranges.append((start, last))
            start = None
            last = None

        if b:
            if start is None:
                start = fn

            last = fn

    if start is not None:
        ranges.append((start, last))

    if min_len > 1:
        return [(s, l) for s, l in ranges if l - s + 1 >= min_len]

    return ranges
