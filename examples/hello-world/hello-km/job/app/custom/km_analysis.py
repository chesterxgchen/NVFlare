from lifelines import KaplanMeierFitter


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
        'timeline': timeline.tolist(),
        'km_estimate': km_estimate.tolist(),
        'event_count': event_count.tolist(),
        'survival_rate': survival_rate.tolist()
    }

