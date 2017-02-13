#!/usr/bin/env python
""" Sleep Talk

Simple script to (attempt to) record sleep talking.

    Author:     Erick Daniszewski
    Date:       12 Feb 2017
    License:    MIT
"""
import pyaudio
import wave
import audioop
import math
import datetime
import os

from collections import deque
from pydub import AudioSegment  # for converting wav to mp3


THRESHOLD = 800  # 800 arbitrarily chosen as default
THRESHOLD_OFFSET = 300  # amount to offset calibration to get new offset
LISTEN_HISTORY = 8  # time in seconds

SILENCE_PRE_SEC = 1   # seconds of recording (before first threshold) to include in recording
SILENCE_POST_SEC = 3  # seconds of recording (since last threshold) before terminating a recording

# configurations for the stream - these represent default values and will be
# updated when a device is selected
stream_config = dict(
    input=True,
    format=pyaudio.paInt16,
    channels=2,
    rate=44100,
    frames_per_buffer=4096
)

# samples per second : rate / chunk size
chunks_per_sec = stream_config['rate'] / stream_config['frames_per_buffer']

p = pyaudio.PyAudio()


def update_stream_config():
    """ Update the global configuration dictionary to use the known configurations
    taken off of the default input device.
    """
    device_info = p.get_default_input_device_info()

    print 'Using Input Device: {}'.format(device_info['name'])

    stream_config.update(dict(
        channels=device_info['maxInputChannels'],
        rate=int(device_info['defaultSampleRate'])
    ))

    for k, v in stream_config.iteritems():
        print '\t{}: {}'.format(k, v)


def calibrate_threshold(stream):
    """

    Args:
        stream:
    """
    global THRESHOLD
    print '* re-calibrating threshold (5s) *'
    old = THRESHOLD

    chunk = stream_config['frames_per_buffer']
    rate = stream_config['rate']

    frame_avgs = []
    for _ in xrange(0, int(rate / chunk * 5)):
        data = stream.read(chunk)
        frame_avgs.append(math.sqrt(abs(audioop.avg(data, 4))))

    avg = None
    if frame_avgs:
        avg = sum(frame_avgs) / len(frame_avgs)

    if not avg:
        print '[unable to re-calibrate - threshold remaining at {}]'.format(old)
    else:
        THRESHOLD = avg + THRESHOLD_OFFSET
        print '[successfully re-calibrated threshold (was {}, now is {})]'.format(old, THRESHOLD)


def listen(stream):
    """

    Args:
        stream:
    """
    chunk = stream_config['frames_per_buffer']
    rate = stream_config['rate']

    # the data structure within which the main listening will be stored
    listen_history = deque(maxlen=(rate / chunk) * LISTEN_HISTORY)

    # the data structure within which the data to be recorded+saved will be stored
    record_data = []

    # flag used to determine whether we are currently recording, or just listening
    recording = False

    # counter for the number of reads that occur when recording during which noise
    # under the threshold was heard.
    under_count = 0

    # fixme - could make the listen time configurable.
    while True:
        data = stream.read(chunk)

        # if the average audio signal is below the threshold for this
        # read, we will just add it to the listening history and move
        # on.
        if math.sqrt(abs(audioop.avg(data, 4))) < THRESHOLD:
            # if we are recording and under the threshold, check the under count
            # to determine whether we should stop recording
            if recording:
                # FIXME - 30 should change here....
                if under_count > (chunks_per_sec * SILENCE_POST_SEC):
                    print ' .. time to stop'
                    recording = False
                    under_count = 0
                    save_recording(listen_history, record_data)
                    print 'saved!'
                    record_data = []

                else:
                    print '  .. recording'
                    record_data.append(data)
                    under_count += 1

            # if under the threshold, but not recording, just add it to the listen history
            else:
                listen_history.append(data)

        # otherwise, the signal is above the threshold. a signal above the
        # threshold should result in the start of a recording (if not already
        # started) or the continuation of a recording.
        else:
            print 'above threshold'
            # set recording flag
            recording = True

            # reset under threshold count
            under_count = 0

            # add the data to the recording collection
            record_data.append(data)


def save_recording(listen_history, record_data):
    """
    """
    to_save = []

    print 'saving recording'

    # prepend some of the history
    for _ in range(chunks_per_sec * SILENCE_PRE_SEC):
        try:
            to_save.append(listen_history.pop())
        except Exception:
            pass

    to_save.reverse()

    # clear out the history now for the next run
    listen_history.clear()

    to_save.extend(record_data)

    print 'writing to wav file'

    filename = '{!s}'.format(datetime.datetime.utcnow().strftime('%B %d %Y %H.%M.%S'))
    wf = wave.open(filename + '.wav', 'wb')
    wf.setnchannels(stream_config['channels'])
    wf.setsampwidth(p.get_sample_size(stream_config['format']))
    wf.setframerate(stream_config['rate'])
    wf.writeframes(b''.join(to_save))
    wf.close()

    print 'converting to mp3'
    AudioSegment.from_wav(filename + '.wav').export(filename + '.mp3', format='mp3')

    print 'removing wav'
    os.remove(filename + '.wav')


if __name__ == '__main__':
    update_stream_config()

    stream = p.open(**stream_config)

    calibrate_threshold(stream)

    listen(stream)
