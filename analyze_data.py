import os
import sys
import subprocess

# Auto-install missing packages on startup
required_packages = {
    'pandas': 'pandas',
    'numpy': 'numpy',
    'matplotlib': 'matplotlib',
    'seaborn': 'seaborn',
    'scipy': 'scipy',
    'statsmodels': 'statsmodels',
    'scikit-learn': 'sklearn',
    'openpyxl': 'openpyxl'  # Needed for excel files
}

for package, import_name in required_packages.items():
    try:
        __import__(import_name)
    except ImportError:
        print(f"\n[INFO] Missing package '{package}'. Installing automatically via pip...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"[SUCCESS] Installed '{package}' successfully.\n")
        except Exception as e:
            print(f"[ERROR] Failed to install '{package}': {e}")
            print(f"Please run 'pip install {package}' manually.")
            sys.exit(1)

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

# Stats & Math
from scipy import stats
from statsmodels.tsa.stattools import adfuller

# Machine Learning
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, IsolationForest
from sklearn.metrics import r2_score, mean_squared_error, accuracy_score, classification_report
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans

def load_data(file_path):
    """Loads CSV or Excel files automatically."""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.csv':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
                sep = ';' if ';' in first_line else ','
            return pd.read_csv(file_path, sep=sep)
        elif ext in ['.xls', '.xlsx']:
            return pd.read_excel(file_path)
        else:
            raise ValueError("Unsupported format. Please supply a CSV or Excel file.")
    except Exception as e:
        print(f"\n[ERROR] Loading file: {e}")
        return None

def auto_detect_types(df):
    """Identifies datetime, numeric, and categorical columns."""
    datetime_cols = []
    numeric_cols = []
    categorical_cols = []
    
    for col in df.columns:
        if df[col].dtype == 'object':
            try:
                sample = df[col].dropna().head(5)
                if len(sample) > 0:
                    for s in sample:
                        pd.to_datetime(str(s))
                    df[col] = pd.to_datetime(df[col])
                    datetime_cols.append(col)
                    continue
            except:
                pass
        
        if pd.api.types.is_numeric_dtype(df[col]):
            if df[col].nunique() < 10:
                categorical_cols.append(col)
            else:
                numeric_cols.append(col)
        else:
            categorical_cols.append(col)
            
    return datetime_cols, numeric_cols, categorical_cols

def clean_data(df, datetime_cols, numeric_cols, categorical_cols):
    """Imputes missing data and formats dates."""
    df_clean = df.copy()
    # Impute numeric with median
    for col in numeric_cols:
        if df_clean[col].isnull().any():
            df_clean[col].fillna(df_clean[col].median(), inplace=True)
            
    # Impute categorical with mode
    for col in categorical_cols:
        if df_clean[col].isnull().any():
            mode_val = df_clean[col].mode()
            fill = mode_val[0] if not mode_val.empty else "Missing"
            df_clean[col].fillna(fill, inplace=True)
            
    if datetime_cols:
        df_clean.sort_values(by=datetime_cols[0], inplace=True)
        df_clean.index = df_clean[datetime_cols[0]]
        
    return df_clean

def run_data_integrity_audit(df):
    """Audits data quality, duplicate counts, and null rates."""
    print("\n" + "=" * 80)
    print("  STAGE 1: DATA INTEGRITY & QUALITY AUDIT")
    print("=" * 80)
    
    total_rows = len(df)
    duplicates = df.duplicated().sum()
    null_report = df.isnull().sum()
    null_pct = (null_report / total_rows) * 100
    
    integrity_df = pd.DataFrame({
        'Null Count': null_report,
        'Null %': null_pct,
        'Unique Values': df.nunique(),
        'Data Type': df.dtypes
    })
    
    print(f"Total Rows:       {total_rows:,}")
    print(f"Duplicate Rows:   {duplicates:,}")
    print("\nColumn Integrity Report:")
    print(integrity_df.to_string())

def run_statistical_distribution_tests(df, numeric_cols, categorical_cols):
    """Runs Shapiro-Wilk normality tests, skewness, ANOVA variance checks."""
    print("\n" + "=" * 80)
    print("  STAGE 2: DISTRIBUTIONS & INFERENTIAL STATISTICAL TESTS")
    print("=" * 80)
    
    print(f"{'Metric Column':<20} | {'Skewness':<10} | {'Kurtosis':<10} | {'Normality p-value':<20} | {'Verdict':<15}")
    print("-" * 80)
    
    for col in numeric_cols:
        skew = df[col].skew()
        kurt = df[col].kurt()
        
        sample = df[col].dropna().head(5000)
        if len(sample) >= 3:
            _, p_val = stats.shapiro(sample)
            verdict = "Normal" if p_val > 0.05 else "Skewed/Non-Normal"
            p_val_str = f"{p_val:.6f}"
        else:
            p_val_str = "N/A"
            verdict = "Low Sample"
            
        print(f"{col:<20} | {skew:<+10.4f} | {kurt:<+10.4f} | {p_val_str:<20} | {verdict:<15}")
        
    if categorical_cols and numeric_cols:
        print("\nGroup Variance Checks (One-Way ANOVA):")
        print(f"{'Category Column':<20} | {'Numeric Metric':<20} | {'F-Statistic':<15} | {'p-value':<15} | {'Verdict':<15}")
        print("-" * 90)
        
        for cat in categorical_cols[:3]:
            if df[cat].nunique() > 15 or df[cat].nunique() < 2:
                continue
            groups = df[cat].unique()
            for num in numeric_cols[:3]:
                group_data = [df[df[cat] == g][num].values for g in groups if len(df[df[cat] == g]) > 5]
                if len(group_data) < 2:
                    continue
                f_stat, p_val = stats.f_oneway(*group_data)
                verdict = "Sig Difference" if p_val < 0.05 else "No Difference"
                print(f"{cat:<20} | {num:<20} | {f_stat:<15.4f} | {p_val:<15.6f} | {verdict:<15}")

def run_advanced_anomaly_detection(df, numeric_cols):
    """Detects outliers using Isolation Forest."""
    if len(numeric_cols) < 2:
        print("\n[ERROR] Anomaly detection requires at least 2 numeric columns.")
        return
    print("\n" + "=" * 80)
    print("  STAGE 3: ADVANCED OUTLIER & ANOMALY DETECTION (ISOLATION FOREST)")
    print("=" * 80)
    
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(df[numeric_cols])
    
    iso = IsolationForest(contamination=0.01, random_state=42)
    df['anomaly_label'] = iso.fit_predict(scaled_data)
    
    anomalies = df[df['anomaly_label'] == -1]
    print(f"Detected {len(anomalies)} multi-variable outliers (1.0% contamination limit):")
    if len(anomalies) > 0:
        print(anomalies[numeric_cols].head(10).to_string())

def run_unsupervised_clustering(df, numeric_cols, output_dir="."):
    """Performs PCA and K-Means clustering (Data Segmentation)."""
    if len(numeric_cols) < 2:
        print("\n[ERROR] Clustering requires at least 2 numeric columns.")
        return
    print("\n" + "=" * 80)
    print("  STAGE 4: UNSUPERVISED CLUSTERING & SEGMENTATION (PCA + K-MEANS)")
    print("=" * 80)
    
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(df[numeric_cols])
    
    pca = PCA(n_components=2)
    pca_data = pca.fit_transform(scaled_data)
    df['pca_1'] = pca_data[:, 0]
    df['pca_2'] = pca_data[:, 1]
    
    kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
    df['cluster_label'] = kmeans.fit_predict(scaled_data)
    
    print("K-Means Cluster Counts & Profile:")
    counts = df['cluster_label'].value_counts()
    for cluster, count in counts.items():
        print(f"  Cluster {cluster}: {count:,} records")
        
    plt.figure(figsize=(10, 6))
    sns.scatterplot(x='pca_1', y='pca_2', hue='cluster_label', palette='viridis', data=df, alpha=0.7)
    plt.title("Data Segmentation Clusters (PCA projection)")
    plt.xlabel("Principal Component 1")
    plt.ylabel("Principal Component 2")
    plt.tight_layout()
    plot_path = os.path.join(output_dir, "segmentation_clusters.png")
    plt.savefig(plot_path)
    plt.close()
    print(f"  Saved cluster plot to {plot_path}")

def run_time_series_analysis(df, datetime_cols, numeric_cols, output_dir="."):
    """Performs trends plotting and Augmented Dickey-Fuller stationarity check."""
    if not datetime_cols or not numeric_cols:
        print("\n[ERROR] Trend analysis requires at least one datetime column and one numeric column.")
        return
    print("\n" + "=" * 80)
    print("  STAGE 5: TIME-SERIES TRENDS & STATIONARITY ANALYSIS")
    print("=" * 80)
    
    # 1. ADF stationarity test
    print("Augmented Dickey-Fuller (ADF) Stationarity Audit:")
    for col in numeric_cols[:3]:
        series = df[col].dropna()
        if len(series) < 20:
            continue
        try:
            res = adfuller(series.values)
            p_val = res[1]
            stat = res[0]
            verdict = "Yes (Stationary)" if p_val < 0.05 else "No (Trended)"
            print(f"  {col:<20} | Stat: {stat:<10.4f} | p-value: {p_val:<10.6f} | Stationary: {verdict}")
        except:
            pass
            
    # 2. Trend plotting
    df_resampled = df[numeric_cols].resample('ME').mean() if len(df) > 30 else df[numeric_cols]
    plt.figure(figsize=(12, 6))
    for col in numeric_cols[:3]:
        plt.plot(df_resampled.index, df_resampled[col], marker='o', label=col)
    plt.title("Business Metric Trends Over Time")
    plt.xlabel("Date")
    plt.ylabel("Value")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plot_path = os.path.join(output_dir, "time_trends.png")
    plt.savefig(plot_path)
    plt.close()
    print(f"  Saved time trend plot to {plot_path}")

def run_supervised_predictions(df, target_col, numeric_cols, categorical_cols):
    """Trains a Random Forest classifier/regressor and outputs feature importances."""
    print("\n" + "=" * 80)
    print(f"  STAGE 6: SUPERVISED MACHINE LEARNING FORECASTING")
    print("=" * 80)
    
    # Clean output label columns from features
    feature_cols = [c for c in numeric_cols + categorical_cols if c != target_col and c != 'cluster_label' and c != 'anomaly_label' and c != 'pca_1' and c != 'pca_2']
    
    X = df[feature_cols].copy()
    y = df[target_col].copy()
    
    # Label encode categorical features
    for col in X.columns:
        if X[col].dtype == 'object' or pd.api.types.is_categorical_dtype(X[col]):
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col].astype(str))
            
    is_classification = False
    if y.dtype == 'object' or y.nunique() < 10:
        is_classification = True
        le_y = LabelEncoder()
        y = le_y.fit_transform(y.astype(str))
        print(f"Target variable '{target_col}' detected as: CLASSIFICATION")
    else:
        print(f"Target variable '{target_col}' detected as: REGRESSION")
        
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    if is_classification:
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        print(f"  Accuracy Score: {acc * 100:.2f}%")
        print("\nDetailed Performance Matrix:")
        print(classification_report(y_test, preds))
    else:
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        r2 = r2_score(y_test, preds)
        rmse = np.sqrt(mean_squared_error(y_test, preds))
        print(f"  R-Squared (Explanatory Power): {r2:.4f}")
        print(f"  Root Mean Squared Error (RMSE): {rmse:.4f}")
        
    # Feature importance
    importances = model.feature_importances_
    feat_imp = pd.Series(importances, index=feature_cols).sort_values(ascending=False)
    print("\nTop 5 Metric Drivers (Feature Importances):")
    for feat, imp in feat_imp.head(5).items():
        print(f"  {feat:<25} : {imp * 100:.2f}%")

def generate_html_report(df, numeric_cols, output_path):
    """Generates an HTML dashboard summary."""
    desc_df = df[numeric_cols].describe().T
    desc_html = desc_df[['mean', 'std', 'min', '50%', 'max']].to_html(classes='table table-striped')
    
    corr_img = "correlation_heatmap.png" if os.path.exists("correlation_heatmap.png") else ""
    clust_img = "segmentation_clusters.png" if os.path.exists("segmentation_clusters.png") else ""
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Data Analysis Report</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{ background-color: #f8f9fa; padding: 30px; }}
            .card {{ margin-bottom: 25px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
            h1 {{ font-weight: 700; margin-bottom: 30px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Business Intelligence & Data Analysis Report</h1>
            <p class="text-muted">Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <div class="card card-body">
                <h3 class="card-title">Descriptive Summary Table</h3>
                {desc_html}
            </div>
            
            <div class="row">
                {f'<div class="col-md-6"><div class="card card-body text-center"><h3>Correlation Map</h3><img src="{corr_img}" class="img-fluid rounded"></div></div>' if corr_img else ''}
                {f'<div class="col-md-6"><div class="card card-body text-center"><h3>Segmentation Clusters</h3><img src="{clust_img}" class="img-fluid rounded"></div></div>' if clust_img else ''}
            </div>
        </div>
    </body>
    </html>
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"\nGenerated HTML Report: {output_path}")

def run_correlation_heatmap(df, numeric_cols, output_dir="."):
    """Helper to save correlation heatmap."""
    if len(numeric_cols) < 2:
        return
    corr = df[numeric_cols].corr()
    plt.figure(figsize=(10, 8))
    sns.heatmap(corr, annot=True, cmap='coolwarm', fmt=".2f", linewidths=0.5)
    plt.title("Correlation Matrix Heatmap")
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "correlation_heatmap.png"))
    plt.close()

def interactive_loop():
    print("=" * 80)
    print("  INTERACTIVE DATA ANALYTICS & BUSINESS INTELLIGENCE CONSOLE")
    print("=" * 80)
    
    # 1. Ask for file
    while True:
        file_path = input("Enter the path to your CSV or Excel file (or 'q' to quit): ").strip()
        if file_path.lower() == 'q':
            sys.exit(0)
        if os.path.exists(file_path):
            break
        print(f"[ERROR] File not found at '{file_path}'. Please try again.")
        
    df = load_data(file_path)
    if df is None:
        sys.exit(1)
        
    print(f"\nLoaded successfully: {df.shape[0]} rows | {df.shape[1]} columns")
    
    # Automatically scan types and clean
    date_cols, num_cols, cat_cols = auto_detect_types(df)
    df = clean_data(df, date_cols, num_cols, cat_cols)
    
    # 2. Main menu loop
    while True:
        print("\n" + "-" * 50)
        print("  ANALYSIS OPTIONS MENU")
        print("-" * 50)
        print(" [1] Run Data Integrity & Quality Audit")
        print(" [2] Run Stats Tests & Variance Checks (Normality, ANOVA)")
        print(" [3] Scan for Outliers & Anomalies (Isolation Forest)")
        print(" [4] Run Customer Segmentation & Clustering (K-Means)")
        print(" [5] Run Time-Series Trends & Stationarity Analysis")
        print(" [6] Train Machine Learning Model (Predict/Forecast)")
        print(" [7] Generate HTML Summary Dashboard")
        print(" [8] Run ALL Analysis Stages")
        print(" [9] Load a Different File")
        print(" [10] Exit Program")
        
        choice = input("\nSelect an option [1-10]: ").strip()
        
        if choice == '1':
            run_data_integrity_audit(df)
        elif choice == '2':
            if num_cols:
                run_statistical_distribution_tests(df, num_cols, cat_cols)
            else:
                print("\n[ERROR] No numeric columns found.")
        elif choice == '3':
            run_advanced_anomaly_detection(df, num_cols)
        elif choice == '4':
            run_unsupervised_clustering(df, num_cols)
        elif choice == '5':
            run_time_series_analysis(df, date_cols, num_cols)
        elif choice == '6':
            print("\nAvailable columns for prediction:")
            for i, col in enumerate(df.columns):
                print(f"  [{i}] {col}")
            target = input("\nEnter the name (or number) of the target column: ").strip()
            if target.isdigit():
                idx = int(target)
                if 0 <= idx < len(df.columns):
                    target = df.columns[idx]
            if target in df.columns:
                run_supervised_predictions(df, target, num_cols, cat_cols)
            else:
                print(f"\n[ERROR] Column '{target}' not found.")
        elif choice == '7':
            if num_cols:
                run_correlation_heatmap(df, num_cols)
                generate_html_report(df, num_cols, "analysis_report.html")
            else:
                print("\n[ERROR] No numeric columns found to generate dashboard charts.")
        elif choice == '8':
            run_data_integrity_audit(df)
            if num_cols:
                run_statistical_distribution_tests(df, num_cols, cat_cols)
                run_advanced_anomaly_detection(df, num_cols)
                run_correlation_heatmap(df, num_cols)
                run_unsupervised_clustering(df, num_cols)
            if date_cols and num_cols:
                run_time_series_analysis(df, date_cols, num_cols)
            if num_cols:
                generate_html_report(df, num_cols, "analysis_report.html")
            print("\nALL stages completed successfully.")
        elif choice == '9':
            print("\nRestarting loop for new file...")
            return interactive_loop()
        elif choice == '10' or choice.lower() == 'q':
            print("\nExiting program. Goodbye!")
            sys.exit(0)
        else:
            print("\n[ERROR] Invalid option. Please select between 1 and 10.")
            
        input("\nPress [Enter] to return to the Menu...")

if __name__ == '__main__':
    interactive_loop()
