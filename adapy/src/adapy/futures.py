#!/usr/bin/env python

# Copyright (c) 2014, Carnegie Mellon University
# All rights reserved.
# Authors: Tekin Mericli <tekin@cmu.edu>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
# - Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
# - Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# - Neither the name of Carnegie Mellon University nor the names of its
#   contributors may be used to endorse or promote products derived from this
#   software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.


class FutureError(Exception):
    pass


class TimeoutError(FutureError):
    pass


class CancelledError(FutureError):
    pass


class Future(object):
    import logging

    logger = logging.getLogger('future')

    def __init__(self):
        from Queue import Queue
        from threading import Condition, RLock

        self.lock = RLock()

        self._is_done = False
        self._is_error = False
        self._is_cancelled = False

        self._handle = None
        self._result = None
        self._exception = None

        self._condition = Condition(self.lock)
        self._callbacks = []

    def done(self):
        """ Return True if the call was cancelled or finished running. """
        with self.lock:
            return self._is_done

    def cancel(self):
        """ Attempt to cancel the call. """
        raise NotImplementedError('Cancelling is not supported.')

    def cancelled(self):
        """ Return True if the call was successfully cancelled. """
        with self.lock:
            return self._is_done and self._is_cancelled

    def result(self, timeout=None):
        """ Return the value returned by the call.

        If the call hasn't yet completed then this method will wait up to
        timeout seconds. If the call hasn't completed in timeout seconds, then
        a TimeoutError will be raised. timeout can be an int or float. If
        timeout is not specified or None, there is no limit to the wait time.

        If the future is cancelled before completing then CancelledError will
        be raised.

        If the call raised, this method will raise the same exception.

        @param timeout: seconds to wait for a result, None to wait forever
        @type  timeout: int or float or None
        @returns: the result of the call wrapped by the future
        """
        with self.lock:
            self._condition.wait(timeout)

            if not self._is_done:
                raise TimeoutError()
            elif self._is_cancelled:
                raise CancelledError()
            elif self._exception is not None:
                raise self._exception
            else:
                return self._result

    def exception(self, timeout=None):
        """ Return the exception raised by the call.

        If the call hasn't yet completed then this method will wait up to
        timeout seconds. If the call hasn't completed in timeout seconds, then
        a TimeoutError will be raised. timeout can be an int or float. If
        timeout is not specified or None, there is no limit to the wait time.

        If the future is cancelled before completing then CancelledError will
        be raised.

        If the call completed without raising, None is returned.

        @param timeout: Time, in seconds, to wait for a result
        @type  timeout: float 
        """
        with self.lock:
            self._condition.wait(timeout)

            if not self._is_done:
                raise TimeoutError()
            elif self._is_cancelled:
                raise CancelledError()
            elif self._exception is not None:
                return self._exception
            else:
                return None

    def add_done_callback(self, fn):
        """ Attaches the callable fn to the future.

        fn will be called, with the future as its only argument, when the
        future is cancelled or finishes running. If fn was already added as a
        callback, this will raise an InternalError.

        Added callables are called in the order that they were added and are
        always called in a thread belonging to the process that added them. If
        the callable raises a Exception subclass, it will be logged and
        ignored. If the callable raises a BaseException subclass, the behavior
        is undefined.

        If the future has already completed or been cancelled, fn will be
        called immediately.

        @param fn: Function to call when done
        @type  fn: function 
        """
        with self.lock:
            if self._is_done:
                if fn in self._callbacks:
                    raise ValueError('Callback is already registered.')

                self._callbacks.append(fn)
                do_call = False
            else:
                do_call = True

        if do_call:
            fn(self)

    def remove_done_callback(self, fn):
        """ Removes the callable fn to the future.

        If fn is not registered as a callback, this will raise an Exception.
        @param fn: Function to be removed
        @type  fn: function
        """
        with self.lock:
            try:
                self._callbacks.remove(fn)
            except ValueError:
                raise ValueError('Callback was not registered.')

    def set_result(self, result):
        """ Set the result of this Future. """
        self._result = result
        self._set_done()

    def set_cancelled(self):
        """ Flag this Future as being cancelled. """
        self._is_cancelled = True
        self._set_done()

    def set_exception(self, exception):
        """ Indicates that an exception has occurred. """
        self._exception = exception
        self._set_done()

    def _set_done(self):
        """ Mark this future as done and return a callback function. """
        with self.lock:
            if self._is_done:
                raise InternalError('This future is already done.')

            self._is_done = True
            callbacks = list(self._callbacks)

            self._condition.notify_all()

        for callback_fn in callbacks:
            try:
                callback_fn(self)
            except Exception as e:
                self.logger.exception('Callback raised an exception.')
