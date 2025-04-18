
# Key Insights from Exercise Motion Sensor Data Analysis

## Overview
- Dataset contains **9,009 records** from **5 participants** performing various weightlifting exercises
- Data includes accelerometer and gyroscope readings in 3 axes (x, y, z)
- Exercises performed with either **heavy** or **medium** weights, plus rest periods (sitting/standing)

## Exercise Signature Patterns

### 1. Distinct Sensor Profiles
Each exercise shows a unique "signature" in sensor readings:
- **Bench Press**: High positive Y-axis acceleration (~0.95g), moderate negative X-axis
- **Overhead Press**: Most negative X-axis acceleration (-0.24g), high positive Y-axis
- **Deadlift & Row**: Similar patterns with strongly negative Y-axis (~-1.02g)
- **Squat**: Unique pattern with positive X-axis and moderate Y-axis values
- **Rest Periods**: Highest X-axis acceleration and distinctive gyroscope patterns

### 2. Weight Category Differences
Heavy vs. Medium weight categories show clear differences:
- **Gyroscope Z-axis** shows the largest differences between weight categories
- **Bench Press**: Shows 30-40% higher gyroscope readings in heavy category
- **Overhead Press**: Exhibits the largest differences between weight categories
- **Deadlift**: Shows distinct accelerometer patterns between categories

### 3. Participant Variations
- Participants have individual "styles" when performing the same exercises
- **Participant A** has the most balanced distribution across exercise types
- **Participant B** shows distinctive patterns in squat and overhead press
- Sensor reading averages vary significantly between participants

### 4. Exercise Variability
- **Rest periods** show the highest variability in sensor readings
- **Squats** have high variability in accelerometer X-axis
- **Overhead Press** exhibits high gyroscope Z-axis variability
- **Bench Press** demonstrates consistent accelerometer Y-axis patterns

### 5. Pattern Identification
- PCA analysis shows clear clustering of exercise types
- Principal components are primarily driven by:
  - **PC1**: Accelerometer readings (especially X and Z axes)
  - **PC2**: Gyroscope X and Z axes
- Exercise types form distinct clusters, particularly separating upper body from lower body exercises
