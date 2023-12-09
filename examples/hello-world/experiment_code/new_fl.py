# fed_avg
from abc import ABC
from typing import List, Optional

import nvflare.server as flare_ctrl

from nvflare.app_common import abstract
from nvflare.app_common.abstract.fl_model import FLModel
from .train import train


#
# def model_init_fn() -> FLModel:
#     pass
#
# def model_aggr_fn(models : List[FLModel]) -> FLModel:
#     pass


# hgw do I know this go to the aggregator site

class FLApp(ABC):
    @abstract
    def set_site_name(self, site_name: str):
        pass


def stop_condition(current_round,
                   total_rounds,
                   metric: float,
                   max_metric: Optional[flot] = None,
                   min_metric: Optional[flot] = None) -> True:
    if current_round == total_rounds:
        return True
    if min_metric and metric <= min_metric:
        return True
    if max_metric and metric >= max_metric:
        return True

    return False


class FedAvg(FLApp):
    def __init__(self,
                 total_rounds: int,
                 stop_accuracy,
                 min_sites: int,
                 sites: List[str],
                 model_init_fn,
                 stop_fn,
                 model_aggr_fn,
                 model_select_fn,
                 persist_fn,
                 ):
        self.total_rounds = total_rounds
        self.stop_accuracy = stop_accuracy
        self.min_sites = min_sites
        self.sites = sites
        self.model_init_fn = model_init_fn
        self.model_aggr_fn = model_aggr_fn
        self.model_select_fn = model_select_fn
        self.persist_fn = persist_fn
        self.stop_fn = stop_fn
        self.site_name = None

        flare_ctrl.init()

    def get_site_name(self):
        return self.site_name

    def set_site_name(self, site_name: str):
        self.site_name = site_name

    def _run(self):
        accuracy = 0
        curr_round = 0
        total_rounds = self.total_rounds
        model = self.model_init_fn()
        best_model = model
        other_sites = [client for client in self.sites if client != self.get_site_name()]
        while not stop_condition(curr_round, total_rounds, accuracy, max_metric=self.stop_accuracy):
            flare_ctrl.broadcast(model, other_sites)

            # blocking call, wait for min sites. not consider streaming version at the moment
            results: List[FLModel] = flare_ctrl.receive_model(self.min_sites)
            model = self.model_aggr_fn(results)
            best_model = self.model_select_fn(model, best_model)

        self.persist_fn.save_model(best_model)


class Cyclic(FLApp):
    def __init__(self,
                 total_rounds: int,
                 min_sites: int,
                 sites: List[str],
                 model_init_fn,
                 model_select_fn,
                 persist_fn,
                 ):
        self.total_rounds = total_rounds
        self.min_sites = min_sites
        self.sites = sites
        self.model_init_fn = model_init_fn
        self.model_select_fn = model_select_fn
        self.persist_fn = persist_fn
        self.site_name = None
        flare_ctrl.init()

    def get_site_name(self):
        return self.site_name

    def set_site_name(self, site_name: str):
        self.site_name = site_name

    def _run(self):
        accuracy = 0
        curr_round = 0
        total_rounds = self.total_rounds
        model = self.model_init_fn()
        best_model = model
        other_sites = [client for client in self.sites if client != self.get_site_name()]
        while accuracy < 0.8 or curr_round < total_rounds:
            for site in other_sites:
                flare_ctrl.send(model, site)
                results: List[FLModel] = flare_ctrl.receive_model(self.min_sites)
                model = results[0]
                best_model = self.model_select_fn(model, best_model)

        self.persist_fn.save_model(best_model)


class Swarm(FLApp):
    def __init__(self,
                 total_rounds: int,
                 min_sites: int,
                 sites: List[str],
                 model_init_fn,
                 model_aggr_fn,
                 model_select_fn,
                 persist_fn,
                 ):
        self.total_rounds = total_rounds
        self.min_sites = min_sites
        self.sites = sites
        self.model_init_fn = model_init_fn
        self.model_aggr_fn = model_aggr_fn
        self.model_select_fn = model_select_fn
        self.persist_fn = persist_fn
        self.site_name = None
        flare_ctrl.init()

    def get_site_name(self):
        return self.site_name

    def set_site_name(self, site_name: str):
        self.site_name = site_name

    def run(self):
        accuracy = 0
        curr_round = 0
        total_rounds = self.total_rounds
        model = self.model_init_fn()
        best_model = model
        target_site = self.get_site_name()

        while accuracy < 0.8 or curr_round < total_rounds:
            other_sites = [client for client in self.sites if client != target_site]
            flare_ctrl.broadcast(model, other_sites)
            # blocking call, wait for min sites. not consider streaming version at the moment
            results: List[FLModel] = flare_ctrl.receive_model(self.min_sites)
            model = self.model_aggr_fn(results)
            best_model = self.model_select_fn(model, best_model)
            target_site = self.next_site(other_sites)

        self.persist_fn.save_model(best_model)

    def next_site(self, sites):
        import random
        # Select a random site from the list
        return random.choice(sites)


class App(FLApp):
    def __init__(self,
                 data_path_fn,
                 train_fn,
                 *kwargs):
        self.train_fn = train_fn
        self.data_path_fn = data_path_fn
        self.train_args = kwargs
        self.site_name = None

    def get_site_name(self):
        return self.site_name

    def set_site_name(self, site_name: str):
        self.site_name = site_name

    def run(self):
        self.train_fn(self.train_args)


class Job:
    def __init__(self, name):
        self.name = name

    def to(self, app: FLApp, site: str):
        wf.set_site_name(site)
        pass

    def simulate(self, threads: int):
        pass

    def submit(self):
        pass


job = Job(name="cifar10_fedavg_pt")
wf = FedAvg(min_sites=2, total_rounds=10, sites=["s1", "s2"])
job.to(wf, "server")

job.add_output_filter(filter, "site-1", filter_type="result_filter")
job.add_output_filter(filter, "site-2", filter_type="result_filter")


def get_data_path(site_name: str):
    return f"/tmp/{site_name}/data.csv",


app = App(dataset_path_fn=get_data_path,
          train_fn=train,
          batch_size=1024,
          local_epochs=1000,
          model_path="/tmp/model/check_pt",
          num_workers=1)

job.to(app, "site-1")
job.to(app, "site-2")

job.submit()
