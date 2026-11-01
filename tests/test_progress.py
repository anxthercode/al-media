from al_media.core.progress import LineBuffer, parse_progress


def test_incomplete_and_unknown_progress():
    assert parse_progress("ALM_PROGRESS:download|NA|NA|NA|NA|NA|NA").percent is None
    assert parse_progress("ALM_PROGRESS:download|1|10|NA|NA|NA|NA").percent == 10
    assert parse_progress("ALM_PROGRESS:unknown|1|2|3|4|5|6") is None
    assert parse_progress("ALM_PROGRESS:download|1") is None


def test_channel_buffers_do_not_mix():
    out, err = LineBuffer(), LineBuffer()
    assert out.feed("ALM_PRO") == []
    assert err.feed("ERROR: bad\n") == ["ERROR: bad"]
    assert out.feed("GRESS:postprocess|NA|NA|NA|NA|NA|NA\n") == ["ALM_PROGRESS:postprocess|NA|NA|NA|NA|NA|NA"]


def test_engine_percentage_is_bounded_even_when_estimates_change():
    assert parse_progress("ALM_PROGRESS:download|120|100|NA|NA|NA|NA").percent == 100
    assert parse_progress("ALM_PROGRESS:download|NA|NA|NA|NA|NA|-2%").percent == 0
