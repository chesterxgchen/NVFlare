from client_app_code.train import client_train
from ctrl_app_code.fed_avg import FedAvg2
from nvflare.app_common.job.fed_app import FedApp
from nvflare.app_common.job.fed_wf import FedWF
from nvflare.app_common.job.fl_job import FLJob


def main():
    job = FLJob(name="cifar10_fedavg")
    n_clients = 2
    num_rounds = 10

    fed_avg = FedAvg2(min_clients=n_clients, num_rounds=num_rounds)
    wf_app = FedWF(fl_algo=fed_avg, custom_dir="ctrl_app_code", app_name="server-app")
    job.to(wf_app, site_name="server")

    for i in range(n_clients):
        site_name = f"site-{i + 1}"
        train_config = {"dataset_path": f"/tmp/nvflare/data/site-{i + 1}/data.csv"}
        site_app = FedApp(client_train, train_config, custom_dir="client_app_code", gpu_ids=None)
        job.to(site_app, site_name)

    job.simulate(job_dir="/tmp/nvflare/job/fed_avg")


if __name__ == "__main__":
    main()
