import threading
from queue import Queue

CMD = "command"
CMD_STOP = "STOP"
PAYLOAD = "payload"


class WFQueue:

    def __init__(self, ctrl_queue: Queue, result_queue: Queue):
        self.ctrl_queue = ctrl_queue
        self.result_queue = result_queue
        self.ctrl_queue_lock = threading.Lock()
        self.result_queue_lock = threading.Lock()

    def put_ctrl_msg(self, msg):
        try:
            self.ctrl_queue_lock.acquire()
            self.ctrl_queue.put(msg)
        finally:
            self.ctrl_queue_lock.release()

    def put_result(self, msg):
        try:
            self.result_queue_lock.acquire()
            print("put result into result queue ===", msg)
            self.result_queue.put(msg)
        finally:
            self.result_queue_lock.release()

    def has_ctrl_msg(self) -> bool:
        return not self.ctrl_queue.empty()

    def has_result(self) -> bool:
        return not self.result_queue.empty()

    def ctrl_msg_size(self) -> int:
        return self.ctrl_queue.qsize()

    def result_size(self) -> int:
        return self.result_queue.qsize()

    def get_ctrl_msg(self):
        return self.ctrl_queue.get()

    def get_result(self):
        return self.result_queue.get()

    def put_stop_ctr_msg(self):
        self.put_ctrl_msg({CMD: CMD_STOP, PAYLOAD: {}})
