import logging
import json
import time
import traceback

import requests

# from logstash_async.transport import HttpTransport
from http_logging import AsyncHttpHandler, AsyncHttpTransport


logging.Formatter.converter = time.gmtime


def test_handler(run_localserver, localhost):
    custom_path = 'foo-bar-path'
    custom_header_dict = {'Foo': 'Bar'}

    log_handler = AsyncHttpHandler(
        host=localhost.host,
        port=localhost.port,
        path=custom_path,
        ssl_enable=False,
        ssl_verify=False,
        database_path=localhost.database_path,
        use_logging=True,
        transport=AsyncHttpTransport(
            host=localhost.host,
            port=localhost.port,
            path=custom_path,
            timeout=localhost.timeout,
            ssl_enable=False,
            ssl_verify=False,
            use_logging=True,
            custom_headers=lambda: custom_header_dict,
        ),
    )

    logger = logging.getLogger('test_handler')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(log_handler)

    logged_messages = {
        'debug': 'Does this help debugging?',
        'info': 'Some information...',
        'warning': 'You\'ve been warned!',
    }

    try:
        x = 1/0  # NOQA
    except Exception:
        logged_messages['error'] = traceback.format_exc()

    info_extra = {'foo': 'bar'}

    for level, message in logged_messages.items():
        if level == 'info':
            getattr(logger, level)(message, extra=info_extra)
        else:
            getattr(logger, level)(message)

    # Trigger event flushing to make sure logs are sent to localserver
    # See: https://archive.vn/B6yFt#selection-3749.0-3795.34
    print('Flushing log events...')
    log_handler.flush()

    count = 0

    while True and count <= 10:
        response = requests.post(url=localhost.last_response_url)

        data = response.json()['last_response']

        if data is None:
            time.sleep(0.5)
            count += 1
            continue

        break

    assert response.ok is True
    assert data['request']['http']['method'] == 'POST'
    assert data['request']['url']['path'] == f'/{custom_path}'

    # Verify headers
    for key, val in custom_header_dict.items():
        assert data['request']['headers'].get(key) == val

    recorded_logs = data['request']['body']
    recorded_logs_by_level = {
        log['level']['name']: log
        for log in recorded_logs
    }

    assert len(recorded_logs) == len(logged_messages)

    for level, message in logged_messages.items():
        recorded_log = recorded_logs_by_level[level.upper()]

        assert recorded_log['message'] == str(message)

        if level == 'info':
            assert 'extra' in recorded_log.keys()
            assert recorded_log['extra'] == info_extra
        else:
            assert 'extra' not in recorded_log.keys()
