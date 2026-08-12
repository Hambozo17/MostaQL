from backend import scheduler


def test_scheduler_polls_immediately_and_does_not_overlap(monkeypatch):
    captured = {}

    class FakeScheduler:
        running = False

        def add_job(self, **kwargs):
            captured.update(kwargs)

        def start(self):
            self.running = True

    monkeypatch.setattr(scheduler, "BackgroundScheduler", FakeScheduler)
    monkeypatch.setattr(scheduler.settings, "scraper_poll_interval_seconds", 30.5)

    created = scheduler.start_scheduler()

    assert created.running is True
    assert captured["next_run_time"] is not None
    assert captured["max_instances"] == 1
    assert captured["coalesce"] is True
    assert captured["misfire_grace_time"] == 31
