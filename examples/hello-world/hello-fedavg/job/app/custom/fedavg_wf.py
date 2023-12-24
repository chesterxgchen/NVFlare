import logging
import os.path
import traceback
from enum import Enum
from typing import Dict, Optional

from net import Net
from nvflare.app_common.abstract.fl_model import FLModel, ParamsType
from nvflare.app_common.aggregators.weighted_aggregation_helper import WeightedAggregationHelper
from nvflare.app_common.utils.fl_model_utils import FLModelUtils
from nvflare.app_common.workflows.flare_ctrl.wf_comm import WFComm
from nvflare.app_common.workflows.flare_ctrl.wf_spec import WF
from nvflare.fuel.utils.import_utils import optional_import
from nvflare.security.logging import secure_format_exception


# FedAvg Controller Workflow


class Comparison(Enum):
    LARGER = "larger"
    SMALLER = "smaller"


class Metric(Enum):
    ACCURACY = "accuracy"
    AUC = "auc"
    LOSS = "loss"
    RUNNING_LOSS = "running_loss"


One_Metric_Rule = {
    Metric.ACCURACY: Comparison.LARGER,  # larger is better
    Metric.LOSS: Comparison.SMALLER,  # smaller is better
    Metric.RUNNING_LOSS: Comparison.SMALLER,  # smaller is better
    Metric.AUC: Comparison.LARGER,  # larger is better
}


class FedAvg(WF):
    def __init__(self,
                 min_clients: int,
                 num_rounds: int,
                 output_path: str,
                 start_round: int = 1,
                 early_stop_metrics: dict = None,
                 model_format: str = None
                 ):
        super(FedAvg, self).__init__()
        self.logger = logging.getLogger(self.__class__.__name__)

        self.output_path = output_path
        self.min_clients = min_clients
        self.num_rounds = num_rounds
        self.start_round = start_round
        self.current_round = start_round
        self.mode_format = model_format
        self.best_model: Optional[FLModel] = None

        # early stop metrics values: accuracy, auc, loss, running_loss
        self.early_stop_metrics = early_stop_metrics

        if early_stop_metrics:
            self.logger.info(f"{early_stop_metrics=}")

        # (1) init flare_comm
        self.flare_comm = WFComm(result_check_interval=10)
        self.flare_comm.init(self)

        self.model_writer_fns = {
            "torch": self.pt_save_mode,
            "tensorflow": self.tf_save_mode
        }

    def run(self):
        self.logger.info("============ start Fed Avg Workflow\n \n")
        net = Net()
        model = FLModel(params=net.state_dict(), params_type=ParamsType.FULL)
        for current_round in range(self.start_round, self.start_round + self.num_rounds):
            if self.early_stop_cond(model.metrics, self.early_stop_metrics):
                self.logger.info("early stop condition satisfied, stopping")
                break
            else:
                self.logger.info("early stop condition NOT satisfied, continue")

            self.current_round = current_round

            self.logger.info(f"Round {current_round}/{self.num_rounds} started.")

            self.logger.info("Scatter and Gather")
            sag_results = self.scatter_and_gather(model, current_round)

            self.logger.info("fed avg aggregate")
            aggr_result = self.aggr_fn(sag_results)

            self.logger.info(f"aggregate metrics = {aggr_result.metrics}")

            self.logger.info("update model")

            model = FLModelUtils.update_model(model, aggr_result)

            self.logger.info(f"best model selection")
            self.select_best_model(model)

        self.logger.info(f"save_model")
        self.save_model(self.best_model, self.output_path)

    def scatter_and_gather(self, model: FLModel, current_round):
        msg_payload = {"min_responses": self.min_clients,
                       "current_round": current_round,
                       "num_round": self.num_rounds,
                       "start_round": self.start_round,
                       "data": model}

        # (2) broadcast and wait
        results = self.flare_comm.broadcast_and_wait(msg_payload)
        return results

    def aggr_fn(self, sag_result: Dict[str, Dict[str, FLModel]]) -> FLModel:
        self.logger.info("fed avg aggregate \n")

        if not sag_result:
            raise RuntimeError("input is None or empty")

        task_name, task_result = next(iter(sag_result.items()))

        if not task_result:
            raise RuntimeError("task_result None or empty ")

        self.logger.info(f"aggregating {len(task_result)} update(s) at round {self.current_round}")
        try:
            aggr_params_helper = WeightedAggregationHelper()
            aggr_metrics_helper = WeightedAggregationHelper()
            params_type = None
            for site, fl_model in task_result.items():
                if params_type is None:
                    params_type = fl_model.params_type

                aggr_params_helper.add(
                    data=fl_model.params,
                    weight=self.current_round,
                    contributor_name=site,
                    contribution_round=self.current_round,
                )

                self.logger.info(f"site={site}  {fl_model.metrics=}")
                aggr_metrics_helper.add(
                    data=fl_model.metrics,
                    weight=self.current_round,
                    contributor_name=site,
                    contribution_round=self.current_round,
                )

            aggr_params = aggr_params_helper.get_result()
            aggr_metrics = aggr_metrics_helper.get_result()

            self.logger.info(f"{aggr_metrics=}")

            aggr_result = FLModel(
                params=aggr_params,
                params_type=params_type,
                metrics=aggr_metrics,
                meta={"num_rounds_aggregated": len(task_result),
                      "current_round": self.current_round
                      },
            )
            return aggr_result
        except Exception as e:
            traceback_str = traceback.format_exc()
            raise RuntimeError(f"Exception in aggregate call: {secure_format_exception(e, traceback_str)}")

    def select_best_model(self, curr_model: FLModel):
        if self.best_model is None:
            self.best_model = curr_model
            return

        self.logger.info("compare models")
        if self.is_curr_mode_better(self.best_model, curr_model):
            self.best_model = curr_model

    def save_model(self, model: FLModel, file_path: str):
        writer_fn = self.model_writer_fns.get(self.mode_format, None)
        if writer_fn:
            writer_fn(model, file_path)
        else:
            raise RuntimeError(f"model format '{self.mode_format}' writer function is not available")

    def early_stop_cond(self, metrics: dict, early_stop_metrics: dict):
        self.logger.info(f"early_stop_cond, early_stop_metrics = {early_stop_metrics}, {metrics=}")
        if early_stop_metrics is None or metrics is None:
            return False

        keys = [Metric.ACCURACY, Metric.AUC, Metric.LOSS, Metric.RUNNING_LOSS]
        for key in keys:
            metric_name = key.value
            self.logger.info(f"{key=}, {metric_name=}")
            if metric_name in early_stop_metrics:
                rule = One_Metric_Rule.get(key)
                self.logger.info(f"{metric_name=}, {rule=}")

                if rule == Comparison.LARGER:
                    # larger is better
                    value = metrics.get(metric_name, -1e+10)
                    target_value = early_stop_metrics.get(metric_name, -1e+10)
                    self.logger.info(f"{key=}, {value=}, {target_value=}, is value bigger={(value >= target_value)}")
                    if value >= target_value:
                        return True
                elif rule == Comparison.SMALLER:
                    # smaller is better
                    value = metrics.get(metric_name, 1e+10)
                    target_value = early_stop_metrics.get(metric_name, 1e+10)
                    self.logger.info(f"{key=}, {value=}, {target_value=}, is value smaller={(value <= target_value)}")
                    if value <= target_value:
                        return True
                else:
                    raise ValueError(f"Unknown rule {rule}")

        self.logger.info("early_stop_cond: return false due to default ")

        return False

    def is_curr_mode_better(self, best_model: FLModel, curr_model: FLModel, comp_rule: str = "any") -> bool:
        best_metrics = best_model.metrics
        curr_metrics = curr_model.metrics
        if curr_metrics is None:
            return False

        if comp_rule == "any":
            for metric, metric_value in curr_metrics.items():
                prev_metric_value = best_metrics.get(metric)

                comp_direction = One_Metric_Rule.get(metric)
                if comp_direction == Comparison.LARGER:
                    if metric_value > prev_metric_value:
                        return True
                elif comp_direction == Comparison.SMALLER:
                    if metric_value < prev_metric_value:
                        return True

            return False
        else:  # comp_rule = "all"
            for metric, metric_value in curr_metrics.items():
                prev_metric_value = best_metrics.get(metric)
                comp_direction = One_Metric_Rule.get(metric)
                if comp_direction == Comparison.LARGER:
                    if metric_value <= prev_metric_value:
                        return False
                elif comp_direction == Comparison.SMALLER:
                    if metric_value >= prev_metric_value:
                        return False

            return True

    def pt_save_mode(self, model: FLModel, file_path: str):
        torch, import_flag = optional_import("torch")
        if import_flag:
            dir_name = os.path.dirname(file_path)
            os.makedirs(dir_name, exist_ok=True)

            self.logger.info(f"save best model to {file_path} \n")
            m = model.params
            torch.save(m, file_path)

    def tf_save_mode(self):
        raise NotImplemented
