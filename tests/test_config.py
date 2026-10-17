from al_media import config


def test_portable_settings_persist(tmp_path, monkeypatch):
    (tmp_path / "portable.flag").touch()
    monkeypatch.setattr(config, "app_root", lambda: tmp_path)
    preferences = config.Preferences(folder=str(tmp_path), theme="light", language="uk", concurrency=4)
    preferences.save()
    loaded = config.Preferences.load()
    assert (loaded.theme, loaded.language, loaded.concurrency) == ("light", "uk", 4)
    assert (tmp_path / "data" / "settings.ini").is_file()
