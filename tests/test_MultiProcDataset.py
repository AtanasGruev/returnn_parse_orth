"""
tests for MultiProcDataset
"""

from __future__ import annotations
import _setup_test_env  # noqa
import sys
import numpy
import signal
import contextlib
import unittest
from returnn.util import better_exchook
from returnn.datasets.basic import init_dataset
from returnn.datasets.multi_proc import MultiProcDataset
from returnn.datasets.map import MapDatasetBase
from test_HDFDataset import generate_hdf_from_other
from test_Dataset import dummy_iter_dataset, compare_dataset_seqs


def _sig_alarm_handler(signum, frame):
    raise Exception(f"Alarm (timeout) signal handler")


signal.signal(signal.SIGALRM, _sig_alarm_handler)


@contextlib.contextmanager
def timeout(seconds=10):
    """
    :param seconds: when the context is not closed within this time, an exception will be raised
    """
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)


def test_MultiProcDataset_n1_b1_default():
    hdf_fn = generate_hdf_from_other({"class": "Task12AXDataset", "num_seqs": 23})
    hdf_dataset_dict = {"class": "HDFDataset", "files": [hdf_fn]}
    hdf_dataset = init_dataset(hdf_dataset_dict)
    hdf_dataset_seqs = dummy_iter_dataset(hdf_dataset)

    with timeout():
        mp_dataset = MultiProcDataset(dataset=hdf_dataset_dict, num_workers=1, buffer_size=1)
        mp_dataset.initialize()
        mp_dataset_seqs = dummy_iter_dataset(mp_dataset)

        compare_dataset_seqs(hdf_dataset_seqs, mp_dataset_seqs)


def test_MultiProcDataset_n3_b5_shuffle():
    hdf_fn = generate_hdf_from_other({"class": "Task12AXDataset", "num_seqs": 23})
    hdf_dataset_dict = {"class": "HDFDataset", "files": [hdf_fn], "seq_ordering": "random"}
    hdf_dataset = init_dataset(hdf_dataset_dict)
    hdf_dataset_seqs = dummy_iter_dataset(hdf_dataset)

    with timeout():
        mp_dataset = MultiProcDataset(dataset=hdf_dataset_dict, num_workers=3, buffer_size=5)
        mp_dataset.initialize()
        mp_dataset_seqs = dummy_iter_dataset(mp_dataset)

        compare_dataset_seqs(hdf_dataset_seqs, mp_dataset_seqs)


def test_MultiProcDataset_meta():
    hdf_fn = generate_hdf_from_other({"class": "Task12AXDataset", "num_seqs": 23})
    meta_dataset_dict = {
        "class": "MetaDataset",
        "data_map": {"classes": ("hdf", "classes"), "data": ("hdf", "data")},
        "datasets": {"hdf": {"class": "HDFDataset", "files": [hdf_fn]}},
    }
    meta_dataset = init_dataset(meta_dataset_dict)
    meta_dataset_seqs = dummy_iter_dataset(meta_dataset)

    with timeout():
        mp_dataset = MultiProcDataset(dataset=meta_dataset_dict, num_workers=1, buffer_size=1)
        mp_dataset.initialize()
        mp_dataset_seqs = dummy_iter_dataset(mp_dataset)

        compare_dataset_seqs(meta_dataset_seqs, mp_dataset_seqs)


class _MyCustomMapDatasetException(Exception):
    pass


class _MyCustomMapDatasetThrowingExceptionAtInit(MapDatasetBase):
    def __init__(self):
        super().__init__()
        raise _MyCustomMapDatasetException("test exception at init")


class _MyCustomMapDatasetThrowingExceptionAtItem(MapDatasetBase):
    def __init__(self):
        super().__init__(data_types={"data": {"shape": (None, 3)}})

    def __len__(self):
        return 2

    def __getitem__(self, item):
        if item == 0:
            return {"data": numpy.zeros((5, 3))}
        raise _MyCustomMapDatasetException("test exception at getitem")


def test_MultiProcDataset_exception_at_init():
    with timeout():
        mp_dataset = MultiProcDataset(
            dataset={"class": "MapDatasetWrapper", "map_dataset": _MyCustomMapDatasetThrowingExceptionAtInit},
            num_workers=1,
            buffer_size=1,
        )
        try:
            mp_dataset.initialize()
        except Exception as exc:
            # Accept any exception. We do not properly forward it. But this is ok.
            print("Got expected exception:", exc)
        else:
            raise Exception("Expected exception")


def test_MultiProcDataset_exception_at_item():
    with timeout():
        mp_dataset = MultiProcDataset(
            dataset={"class": "MapDatasetWrapper", "map_dataset": _MyCustomMapDatasetThrowingExceptionAtItem},
            num_workers=1,
            buffer_size=1,
        )
        mp_dataset.initialize()
        try:
            dummy_iter_dataset(mp_dataset)
        except Exception as exc:
            # Accept any exception. We do not properly forward it. But this is ok.
            print("Got expected exception:", exc)
        else:
            raise Exception("Expected exception")


if __name__ == "__main__":
    better_exchook.install()
    if len(sys.argv) <= 1:
        for k, v in sorted(globals().items()):
            if k.startswith("test_"):
                print("-" * 40)
                print("Executing: %s" % k)
                try:
                    v()
                except unittest.SkipTest as exc:
                    print("SkipTest:", exc)
                print("-" * 40)
        print("Finished all tests.")
    else:
        assert len(sys.argv) >= 2
        for arg in sys.argv[1:]:
            print("Executing: %s" % arg)
            if arg in globals():
                globals()[arg]()  # assume function and execute
            else:
                eval(arg)  # assume Python code and execute
