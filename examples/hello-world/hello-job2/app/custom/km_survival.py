import pandas as pd
from lifelines import KaplanMeierFitter

# (1) import nvflare client API
from nvflare.app_common.abstract.fl_model import FLModel, ParamsType

import nvflare.client as flare


def kaplan_meier_analysis(duration, event):
    # Create a Kaplan-Meier estimator
    kmf = KaplanMeierFitter()

    # Fit the model
    kmf.fit(durations=duration, event_observed=event)

    # Get the survival function at all observed time points
    survival_function_at_all_times = kmf.survival_function_

    # Get the timeline (time points)
    timeline = survival_function_at_all_times.index.values

    # Get the KM estimate
    km_estimate = survival_function_at_all_times['KM_estimate'].values

    # Get the event count at each time point
    event_count = kmf.event_table.iloc[:, 0].values  # Assuming the first column is the observed events

    # Get the survival rate at each time point (using the 1st column of the survival function)
    survival_rate = 1 - survival_function_at_all_times.iloc[:, 0].values

    # Return the results
    return {
        'timeline': timeline,
        'km_estimate': km_estimate,
        'event_count': event_count,
        'survival_rate': survival_rate
    }


def load_data():
    data = {
        'duration': [5, 10, 15, 25, 30, 35, 40, 45],
        'event': [1, 0, 1, 1, 1, 0, 0, 1]
    }
    return data


def display_results(results):
    for time_point, km_estimate, event_count, survival_rate in zip(
            results['timeline'], results['km_estimate'], results['event_count'], results['survival_rate']
    ):
        print(
            f"Time: {time_point}, KM Estimate: {km_estimate:.4f}, Event Count: {event_count}, Survival Rate: {survival_rate:.4f}")


def main():
    print("enter main()")
    flare.init()

    df = pd.DataFrame(data=load_data())

    # Perform Kaplan-Meier analysis and get the results
    results = kaplan_meier_analysis(duration=df['duration'], event=df['event'])

    # Display the results
    display_results(results)
    print(f"send result for site = {flare.get_site_name()}")
    model = FLModel(params=results, params_type=ParamsType.FULL)
    flare.send(model)

    print(f"finish send for {flare.get_site_name()}, complete")


if __name__ == "__main__":
    main()


