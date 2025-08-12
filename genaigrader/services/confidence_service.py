import math

def confidence_interval(data, confidence=0.95):
    n = len(data)
    if n < 1:
        raise ValueError("Need at least one data point")
    elif n == 1:
        return (data[0], data[0], data[0])  # Single data point case

    mean = sum(data) / n
    variance = sum((x - mean) ** 2 for x in data) / (n - 1)
    std_dev = math.sqrt(variance)
    std_err = std_dev / math.sqrt(n)

    # z-values for normal distribution
    z_values = {
        0.90: 1.645,
        0.95: 1.96,
        0.99: 2.576
    }

    # t-values for small samples (df = n-1)
    t_values = {
        0.90: [6.314, 2.920, 2.353, 2.132, 2.015, 1.943, 1.895, 1.860, 1.833,
               1.812, 1.796, 1.782, 1.771, 1.761, 1.753, 1.746, 1.740, 1.734,
               1.729, 1.725, 1.721, 1.717, 1.714, 1.711, 1.708, 1.706, 1.703,
               1.701, 1.699],
        0.95: [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262,
               2.228, 2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101,
               2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052,
               2.048, 2.045],
        0.99: [63.657, 9.925, 5.841, 4.604, 4.032, 3.707, 3.499, 3.355, 3.250,
               3.169, 3.106, 3.055, 3.012, 2.977, 2.947, 2.921, 2.898, 2.878,
               2.861, 2.845, 2.831, 2.819, 2.807, 2.797, 2.787, 2.779, 2.771,
               2.763, 2.756]
    }

    if n <= 30:
        t = t_values[confidence][n-2]  # n-2 because index starts at 0 for n=2
    else:
        t = z_values[confidence]

    margin = t * std_err
    return mean, max(mean - margin, 0), mean + margin  # Prevent negative grades

def compute_averages(model_values, value_name):
    """Calculate average values with confidence intervals for each model"""
    model_averages = []
    for model, data in model_values.items():
        values = data.get(value_name, [])  # Safe dictionary access
        if not values:
            continue  # Skip models with no data

        avg, cinf, csup = confidence_interval(values)
        
        model_averages.append({
            'model__description': model,
            'avg': round(avg, 2),
            'yMin': round(cinf, 2),
            'yMax': round(csup, 2),
            'count': len(values)
        })
    
    return model_averages, []