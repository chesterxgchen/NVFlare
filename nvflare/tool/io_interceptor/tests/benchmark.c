#include "../core/interceptor.h"
#include <time.h>
#include <math.h>

#define ITERATIONS 1000
#define SIZES_COUNT 4
#define WARMUP_ITERATIONS 100

typedef struct {
    const char* name;
    double avg_time;
    double min_time;
    double max_time;
    size_t bytes;
} benchmark_result_t;

typedef struct {
    double mean;
    double stddev;
    double percentile_95;
    double percentile_99;
} stats_t;

static size_t test_sizes[] = {
    4 * 1024,      // 4KB
    64 * 1024,     // 64KB
    1024 * 1024,   // 1MB
    10 * 1024 * 1024 // 10MB
};

benchmark_result_t run_benchmark(const char* name, void (*func)(void*, size_t), size_t size) {
    benchmark_result_t result = {
        .name = name,
        .avg_time = 0,
        .min_time = DBL_MAX,
        .max_time = 0,
        .bytes = size
    };
    
    void* data = malloc(size);
    
    // Warmup
    for (int i = 0; i < WARMUP_ITERATIONS; i++) {
        func(data, size);
    }
    
    // Actual benchmark
    double total_time = 0;
    for (int i = 0; i < ITERATIONS; i++) {
        struct timespec start, end;
        clock_gettime(CLOCK_MONOTONIC, &start);
        
        func(data, size);
        
        clock_gettime(CLOCK_MONOTONIC, &end);
        double time = (end.tv_sec - start.tv_sec) + 
                     (end.tv_nsec - start.tv_nsec) / 1e9;
        
        total_time += time;
        result.min_time = fmin(result.min_time, time);
        result.max_time = fmax(result.max_time, time);
    }
    
    result.avg_time = total_time / ITERATIONS;
    free(data);
    return result;
}

stats_t calculate_stats(double* samples, int count) {
    stats_t stats = {0};
    
    // Calculate mean
    double sum = 0;
    for (int i = 0; i < count; i++) {
        sum += samples[i];
    }
    stats.mean = sum / count;
    
    // Calculate standard deviation
    double sum_sq_diff = 0;
    for (int i = 0; i < count; i++) {
        double diff = samples[i] - stats.mean;
        sum_sq_diff += diff * diff;
    }
    stats.stddev = sqrt(sum_sq_diff / count);
    
    // Calculate percentiles (simple method)
    qsort(samples, count, sizeof(double), compare_doubles);
    stats.percentile_95 = samples[(int)(count * 0.95)];
    stats.percentile_99 = samples[(int)(count * 0.99)];
    
    return stats;
}

void print_histogram(const char* title, double* data, int count, int bins) {
    printf("\n%s Histogram:\n", title);
    printf("------------------------------------------------------------\n");
    
    // Find min and max
    double min_val = data[0], max_val = data[0];
    for (int i = 1; i < count; i++) {
        if (data[i] < min_val) min_val = data[i];
        if (data[i] > max_val) max_val = data[i];
    }
    
    // Create histogram
    int histogram[50] = {0};  // Fixed number of bins
    double bin_width = (max_val - min_val) / bins;
    
    for (int i = 0; i < count; i++) {
        int bin = (int)((data[i] - min_val) / bin_width);
        if (bin >= bins) bin = bins - 1;
        histogram[bin]++;
    }
    
    // Print histogram
    int max_count = 0;
    for (int i = 0; i < bins; i++) {
        if (histogram[i] > max_count) max_count = histogram[i];
    }
    
    for (int i = 0; i < bins; i++) {
        printf("%6.2f ms: %s\n",
               min_val + i * bin_width,
               repeat_char('#', histogram[i] * 50 / max_count));
    }
}

void print_results(benchmark_result_t* results, int count) {
    printf("\nPerformance Benchmarks:\n");
    printf("\nDetailed Results:\n");
    printf("%-20s %-10s %-10s %-10s %-10s\n", 
           "Operation", "Size", "Avg(ms)", "Min(ms)", "Max(ms)");
    printf("------------------------------------------------------------\n");
    
    for (int i = 0; i < count; i++) {
        char size_str[32];
        if (results[i].bytes >= 1024*1024) {
            sprintf(size_str, "%.1fMB", results[i].bytes/(1024.0*1024.0));
        } else if (results[i].bytes >= 1024) {
            sprintf(size_str, "%.1fKB", results[i].bytes/1024.0);
        } else {
            sprintf(size_str, "%zuB", results[i].bytes);
        }
        
        printf("%-20s %-10s %-10.3f %-10.3f %-10.3f\n",
               results[i].name,
               size_str,
               results[i].avg_time * 1000,
               results[i].min_time * 1000,
               results[i].max_time * 1000);
    }

    // Add performance comparison summary
    printf("\nPerformance Impact Summary:\n");
    printf("------------------------------------------------------------\n");
    for (int i = 0; i < count; i += 2) {  // Compare pairs of operations
        const char* op_type = strstr(results[i].name, "Write") ? "Write" : "Read";
        double baseline = results[i].avg_time;
        double intercepted = results[i+1].avg_time;
        double overhead = ((intercepted - baseline) / baseline) * 100.0;
        
        printf("%-20s: %.1f%% overhead (%.2fms vs %.2fms)\n",
               op_type,
               overhead,
               baseline * 1000,
               intercepted * 1000);
    }
    
    // Add size-based analysis
    printf("\nSize Impact Analysis:\n");
    printf("------------------------------------------------------------\n");
    printf("%-10s %-20s %-20s\n", "Size", "Plain (MB/s)", "Encrypted (MB/s)");
    
    for (int i = 0; i < count; i += 8) {  // For each size
        double size_mb = results[i].bytes / (1024.0 * 1024.0);
        double plain_throughput = size_mb / results[i].avg_time;
        double encrypted_throughput = size_mb / results[i+1].avg_time;
        
        printf("%-10.1fMB %-20.2f %-20.2f\n",
               size_mb,
               plain_throughput,
               encrypted_throughput);
    }

    // Add statistical analysis
    printf("\nStatistical Analysis:\n");
    printf("------------------------------------------------------------\n");
    printf("%-20s %-10s %-10s %-10s %-10s\n",
           "Operation", "Mean", "StdDev", "P95", "P99");
    
    double samples[ITERATIONS];
    for (int i = 0; i < count; i++) {
        // Calculate statistics for each operation
        stats_t stats = calculate_stats(samples, ITERATIONS);
        
        printf("%-20s %-10.3f %-10.3f %-10.3f %-10.3f\n",
               results[i].name,
               stats.mean * 1000,
               stats.stddev * 1000,
               stats.percentile_95 * 1000,
               stats.percentile_99 * 1000);
        
        // Generate histogram for important operations
        if (strstr(results[i].name, "Encrypted")) {
            print_histogram(results[i].name, samples, ITERATIONS, 20);
        }
    }

    // Add latency distribution analysis
    printf("\nLatency Distribution Analysis:\n");
    printf("------------------------------------------------------------\n");
    for (int i = 0; i < count; i += 2) {
        printf("\n%s vs %s:\n", results[i].name, results[i+1].name);
        printf("  Baseline P50: %.3f ms\n", results[i].avg_time * 1000);
        printf("  Intercepted P50: %.3f ms\n", results[i+1].avg_time * 1000);
        printf("  Latency increase: %.1f%%\n", 
               ((results[i+1].avg_time - results[i].avg_time) / 
                results[i].avg_time) * 100);
    }
}

int main() {
    init_io_interceptor(NULL); // Use default config
    
    benchmark_result_t results[SIZES_COUNT * 8]; // 8 operations per size (4 file + 4 memory)
    int result_idx = 0;
    
    for (int i = 0; i < SIZES_COUNT; i++) {
        size_t size = test_sizes[i];
        
        // Test file operations
        results[result_idx++] = run_benchmark("File Write (Plain)", 
            test_plain_write, size);
        results[result_idx++] = run_benchmark("File Write (Encrypted)", 
            test_encrypted_write, size);
        results[result_idx++] = run_benchmark("File Read (Plain)", 
            test_plain_read, size);
        results[result_idx++] = run_benchmark("File Read (Encrypted)", 
            test_encrypted_read, size);
        
        // Test memory operations
        results[result_idx++] = run_benchmark("Memory Alloc (Normal)", 
            test_normal_alloc, size);
        results[result_idx++] = run_benchmark("Memory Alloc (TEE)", 
            test_tee_alloc, size);
        results[result_idx++] = run_benchmark("Memory Write (Normal)", 
            test_normal_write, size);
        results[result_idx++] = run_benchmark("Memory Write (TEE)", 
            test_tee_write, size);
    }
    
    print_results(results, result_idx);
    cleanup_io_interceptor();
    return 0;
} 