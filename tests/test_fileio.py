"""Атомарная запись: сбой посреди записи не портит прежний файл и не оставляет *.tmp."""
import os

import mido
import pytest

from remap.core import RemapProfile, convert, legacy_profile
from remap.core.fileio import atomic_write_bytes
from remap.core.notemap import NoteMap
from remap.core.notenames import save_notenames


def _boom(*_args, **_kwargs):
    raise OSError("disk full")


def _no_tmp(folder):
    return [p.name for p in folder.iterdir() if p.suffix == ".tmp"] == []


def test_helper_writes_and_replaces(tmp_path):
    dst = tmp_path / "a.bin"
    atomic_write_bytes(dst, b"one")
    atomic_write_bytes(dst, b"two")
    assert dst.read_bytes() == b"two"
    assert _no_tmp(tmp_path)


@pytest.mark.parametrize("target", ["os.replace", "os.fsync"])
def test_helper_failure_keeps_old_file(tmp_path, monkeypatch, target):
    dst = tmp_path / "a.bin"
    dst.write_bytes(b"old")
    monkeypatch.setattr(target, _boom)
    with pytest.raises(OSError, match="disk full"):
        atomic_write_bytes(dst, b"new")
    assert dst.read_bytes() == b"old"
    assert _no_tmp(tmp_path)


def test_convert_failure_keeps_old_output(tmp_path, monkeypatch):
    src = tmp_path / "in.mid"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([mido.Message("note_on", note=36, velocity=100),
                                       mido.Message("note_off", note=36, velocity=0, time=10)]))
    midi.save(str(src))
    dst = tmp_path / "out.mid"
    dst.write_bytes(b"previous output")
    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError, match="disk full"):
        convert(src, dst, legacy_profile())
    assert dst.read_bytes() == b"previous output"
    assert _no_tmp(tmp_path)


def test_save_notenames_failure_keeps_old_file(tmp_path, monkeypatch):
    dst = tmp_path / "map.txt"
    dst.write_bytes(b"previous map")
    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError, match="disk full"):
        save_notenames(NoteMap("m", {36: "Kick"}), dst)
    assert dst.read_bytes() == b"previous map"
    assert _no_tmp(tmp_path)


def test_storage_failure_keeps_old_files(storage, monkeypatch):
    map_id = storage.save_map(NoteMap("m", {36: "Kick"}))
    profile_id = storage.save_profile(RemapProfile(name="p"))
    map_path = storage.maps_dir / f"{map_id}.json"
    profile_path = storage.profiles_dir / f"{profile_id}.json"
    old_map, old_profile = map_path.read_bytes(), profile_path.read_bytes()
    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError, match="disk full"):
        storage.save_map(NoteMap("m", {38: "Snare"}), map_id=map_id, overwrite=True)
    with pytest.raises(OSError, match="disk full"):
        storage.save_profile(RemapProfile(name="p2"), profile_id=profile_id, overwrite=True)
    assert map_path.read_bytes() == old_map
    assert profile_path.read_bytes() == old_profile
    assert _no_tmp(map_path.parent) and _no_tmp(profile_path.parent)
    assert [e.id for e in storage.list_maps()[0]] == [map_id]
