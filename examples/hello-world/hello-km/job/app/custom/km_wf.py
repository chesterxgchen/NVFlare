import json
import os.path
import time

from km_analysis import kaplan_meier_analysis
from nvflare.app_common.workflows.flare_ctrl.communicator import Communicator
from nvflare.app_common.workflows.flare_ctrl.wf_spec import WF


# Server controller


class KM(WF):
    def __init__(self,
                 min_clients: int,
                 output_path: str):
        self.output_path = output_path
        self.min_clients = min_clients
        self.num_rounds = 1
        self.flare_comm = Communicator()
        self.flare_comm.init(self)
        print("sleep for 2 send to let pipe setup")
        time.sleep(2)

    def run(self):
        results = self.start_km_analysis()
        global_res = self.aggr_km_result(results)
        self.save(global_res, self.output_path)

    def start_km_analysis(self):
        msg_payload = {"min_responses": self.min_clients}
        results = self.flare_comm.broadcast(msg_payload)
        return results

    def aggr_km_result(self, task_result: dict):
        print("\n ======= enter aggregate_fn========= \n")
        global_result = {}
        for site, result in task_result.items():
            timelines = result.get("timeline")
            event_counts = result.get("event_count")
            combined_arrays = list(zip(timelines, event_counts))
            g_timelines = global_result.get("timeline", [])
            g_event_counts = global_result.get("event_count", {})
            for t, count in combined_arrays:
                if not t in g_timelines:
                    g_timelines.append(t)
                    g_event_counts[t] = count
                else:
                    prev_count = g_event_counts.get(t)
                    g_event_counts[t] = prev_count + count
            global_result["event_count"] = g_event_counts
            global_result["timeline"] = g_timelines

        g_duration = global_result.get("timeline", [])
        g_event_counts = list(global_result.get("event_count").values())

        g_km_result = kaplan_meier_analysis(g_duration, g_event_counts)

        all_result = task_result.copy()
        all_result["global"] = g_km_result
        return all_result

    def save(self, result: dict, file_path: str):
        print(f"save the {result} to {file_path}")



        dir_name = os.path.dirname(file_path)
        os.makedirs(dir_name, exist_ok=True)
        with open(file_path, 'w') as json_file:
            json.dump(result, json_file, indent=4)
