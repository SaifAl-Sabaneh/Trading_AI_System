import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
import config
from security import logger

class EnsembleTradingModel:
    """
    Layer 2 Ensemble Machine Learning Classifier.
    Combines predictions from Random Forest, Gradient Boosting, 
    Logistic Regression, and CatBoost (if available) to produce high-precision probability estimations.
    """
    def __init__(self, model_type=config.ML_MODEL_TYPE, confidence_threshold=config.CONFIDENCE_THRESHOLD):
        self.model_type = model_type
        self.confidence_threshold = confidence_threshold
        
        # 1. Random Forest (Tree classifier, bagging)
        self.rf_model = RandomForestClassifier(
            n_estimators=150, 
            max_depth=5, 
            min_samples_split=12,
            random_state=42,
            class_weight="balanced"
        )
        
        # 2. Gradient Boosting (Tree classifier, boosting)
        self.gb_model = GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.05,
            max_depth=3,
            random_state=42
        )
        
        # 3. Logistic Regression with Scaling (Linear meta-classifier)
        self.lr_model = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
        )
        
        # 4. CatBoost Classifier (State-of-the-art gradient boosting for categorical/tabular data)
        try:
            from catboost import CatBoostClassifier
            # Configure CatBoost silently
            self.cb_model = CatBoostClassifier(
                iterations=100,
                learning_rate=0.05,
                depth=4,
                verbose=0,
                random_seed=42
            )
            self.cb_available = True
            logger.info("CatBoost library detected and initialized in the Ensemble.")
        except ImportError:
            self.cb_available = False
            logger.warning("CatBoost library not found. Stacking ensemble running on GBDT, RF, and LR.")
            
        # Meta-labeler secondary model
        self.meta_model = RandomForestClassifier(
            n_estimators=100,
            max_depth=4,
            class_weight="balanced",
            random_state=42
        )
        self.meta_model_trained = False
        self.active_features = None
        self.active_features_pruned = False

    def prune_features(self, X, y):
        """
        Ranks features using a Random Forest classifier's built-in importances,
        and selects the top 75% (dropping the bottom 25% of features to prevent overfitting).
        """
        from sklearn.ensemble import RandomForestClassifier
        from security import logger
        
        valid_idx = X.notna().all(axis=1) & y.notna()
        X_clean = X[valid_idx]
        y_clean = y[valid_idx]
        
        if len(y_clean) < 100:
            logger.warning("Insufficient samples to run feature pruning. Using all features.")
            return list(X.columns)
            
        logger.info("Running dynamic feature importance evaluation...")
        
        # Fit a temporary Random Forest to get feature importances
        temp_rf = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        temp_rf.fit(X_clean, y_clean)
        
        importances = temp_rf.feature_importances_
        feature_names = list(X_clean.columns)
        
        # Sort features by importance
        feature_importance_tuples = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)
        
        # Determine number of features to keep (keep top 75%, drop bottom 25%)
        num_keep = max(5, int(len(feature_names) * 0.75)) # Keep at least 5 features
        selected_features = [f[0] for f in feature_importance_tuples[:num_keep]]
        dropped_features = [f[0] for f in feature_importance_tuples[num_keep:]]
        
        logger.info(f"Feature Pruning Complete. Top {len(selected_features)} Features Selected: {selected_features}")
        logger.info(f"Dropped {len(dropped_features)} redundant/noisy features: {dropped_features}")
        
        return selected_features

    def fit(self, X, y):
        """Trains all available sub-models on historical feature set."""
        from sklearn.calibration import CalibratedClassifierCV
        
        valid_idx = X.notna().all(axis=1) & y.notna()
        X_clean = X[valid_idx]
        y_clean = y[valid_idx]
        
        if len(y_clean) == 0:
            raise ValueError("No valid training samples after removing NaNs.")
            
        # Ensure feature pruning runs if it hasn't run yet
        if not self.active_features_pruned:
            self.active_features = self.prune_features(X_clean, y_clean)
            self.active_features_pruned = True
            
        X_clean_pruned = X_clean[self.active_features]
        
        # Ensure classifiers are calibrated
        if not isinstance(self.rf_model, CalibratedClassifierCV):
            self.rf_model = CalibratedClassifierCV(estimator=self.rf_model, method='sigmoid', cv=3)
        if not isinstance(self.gb_model, CalibratedClassifierCV):
            self.gb_model = CalibratedClassifierCV(estimator=self.gb_model, method='sigmoid', cv=3)
        if self.cb_available and not isinstance(self.cb_model, CalibratedClassifierCV):
            self.cb_model = CalibratedClassifierCV(estimator=self.cb_model, method='sigmoid', cv=3)
            
        # Fit standard models
        self.rf_model.fit(X_clean_pruned, y_clean)
        self.gb_model.fit(X_clean_pruned, y_clean)
        self.lr_model.fit(X_clean_pruned, y_clean)
        
        # Fit CatBoost if available
        if self.cb_available:
            self.cb_model.fit(X_clean_pruned, y_clean)

    def fit_meta_model(self, X, y):
        """
        Fits De Prado's meta-labeler on out-of-fold predictions.
        Trains a secondary classifier to verify primary high-confidence signals.
        """
        from sklearn.model_selection import KFold
        from sklearn.base import clone
        from security import logger
        from sklearn.calibration import CalibratedClassifierCV
        
        valid_idx = X.notna().all(axis=1) & y.notna()
        X_clean = X[valid_idx]
        y_clean = y[valid_idx]
        
        # If too few samples, don't attempt meta-labeler training
        if len(y_clean) < 150:
            logger.warning("Insufficient samples to train secondary meta-model. Skipping.")
            self.meta_model_trained = False
            return
            
        # Ensure self.rf_model, etc. are calibrated before cloning
        if not isinstance(self.rf_model, CalibratedClassifierCV):
            self.rf_model = CalibratedClassifierCV(estimator=self.rf_model, method='sigmoid', cv=3)
        if not isinstance(self.gb_model, CalibratedClassifierCV):
            self.gb_model = CalibratedClassifierCV(estimator=self.gb_model, method='sigmoid', cv=3)
        if self.cb_available and not isinstance(self.cb_model, CalibratedClassifierCV):
            self.cb_model = CalibratedClassifierCV(estimator=self.cb_model, method='sigmoid', cv=3)
            
        # Filter features using self.active_features if pruned
        if self.active_features_pruned:
            X_clean_pruned = X_clean[self.active_features]
        else:
            X_clean_pruned = X_clean
            
        # Generate primary model signal probabilities out-of-fold
        oof_probs = np.zeros(len(X_clean))
        kf = KFold(n_splits=3, shuffle=False)
        
        for train_idx, val_idx in kf.split(X_clean_pruned):
            # Clone primary models (prevent state leakage)
            rf_c = clone(self.rf_model)
            gb_c = clone(self.gb_model)
            lr_c = clone(self.lr_model)
            
            X_tr, y_tr = X_clean_pruned.iloc[train_idx], y_clean.iloc[train_idx]
            X_val = X_clean_pruned.iloc[val_idx]
            
            # Fit clones
            rf_c.fit(X_tr, y_tr)
            gb_c.fit(X_tr, y_tr)
            lr_c.fit(X_tr, y_tr)
            
            p_rf = rf_c.predict_proba(X_val)[:, 1]
            p_gb = gb_c.predict_proba(X_val)[:, 1]
            p_lr = lr_c.predict_proba(X_val)[:, 1]
            
            if self.cb_available:
                cb_c = clone(self.cb_model)
                cb_c.fit(X_tr, y_tr)
                p_cb = cb_c.predict_proba(X_val)[:, 1]
                probs = (p_rf + p_gb + p_lr + p_cb) / 4.0
            else:
                probs = (p_rf + p_gb + p_lr) / 3.0
                
            oof_probs[val_idx] = probs
            
        # Identify where primary model generates BUY signals
        buy_signal_mask = oof_probs >= self.confidence_threshold
        
        X_meta = X_clean_pruned[buy_signal_mask]
        y_meta = y_clean[buy_signal_mask]
        
        # We need a minimum number of trade samples with both classes (0 and 1)
        if len(y_meta) < 15 or len(y_meta.unique()) < 2:
            logger.warning(f"OOF generated only {len(y_meta)} buy signals. Insufficient diversity to train meta-model. Skipping.")
            self.meta_model_trained = False
        else:
            self.meta_model.fit(X_meta, y_meta)
            self.meta_model_trained = True
            logger.info(f"Meta-labeling model trained successfully on {len(y_meta)} historical trades.")

    def predict_signals(self, X):
        """
        Generates directional signals by averaging predictions across all ensemble models.
        Applies De Prado's meta-model checks to filter out high-probability losses.
        """
        if not hasattr(self.rf_model, "classes_"):
            raise ValueError("Model is not trained yet. Call fit() first.")
            
        if self.active_features_pruned:
            X_pruned = X[self.active_features]
        else:
            X_pruned = X
            
        p_rf = self.rf_model.predict_proba(X_pruned)[:, 1]
        p_gb = self.gb_model.predict_proba(X_pruned)[:, 1]
        p_lr = self.lr_model.predict_proba(X_pruned)[:, 1]
        
        if self.cb_available:
            p_cb = self.cb_model.predict_proba(X_pruned)[:, 1]
            probs = (p_rf + p_gb + p_lr + p_cb) / 4.0
        else:
            probs = (p_rf + p_gb + p_lr) / 3.0
            
        signals = np.zeros(len(X))
        
        # 1. Primary Model checks
        buy_mask = probs >= self.confidence_threshold
        
        # 2. Filter primary signals with De Prado's Meta-model
        if self.meta_model_trained and np.any(buy_mask):
            # Only evaluate rows where primary model says BUY
            meta_probs = self.meta_model.predict_proba(X_pruned)[:, 1]
            
            # Keep BUY only if meta-model probability of success is >= 50%
            filtered_buy_mask = buy_mask & (meta_probs >= 0.5)
            signals[filtered_buy_mask] = 1
        else:
            signals[buy_mask] = 1
            
        # Sell signals remain as simple threshold breaches (risk mitigation exits)
        sell_mask = probs <= (1.0 - self.confidence_threshold)
        signals[sell_mask] = -1
        
        return signals, probs

    def get_eval_metrics(self, X_test, y_test):
        """Evaluates ensemble metrics on the test partition."""
        from sklearn.metrics import accuracy_score, precision_score
        
        valid_idx = X_test.notna().all(axis=1) & y_test.notna()
        X_clean = X_test[valid_idx]
        y_clean = y_test[valid_idx]
        
        if self.active_features_pruned:
            X_clean_pruned = X_clean[self.active_features]
        else:
            X_clean_pruned = X_clean
            
        p_rf = self.rf_model.predict_proba(X_clean_pruned)[:, 1]
        p_gb = self.gb_model.predict_proba(X_clean_pruned)[:, 1]
        p_lr = self.lr_model.predict_proba(X_clean_pruned)[:, 1]
        
        if self.cb_available:
            p_cb = self.cb_model.predict_proba(X_clean_pruned)[:, 1]
            probs = (p_rf + p_gb + p_lr + p_cb) / 4.0
        else:
            probs = (p_rf + p_gb + p_lr) / 3.0
            
        preds = (probs >= 0.5).astype(int)
        acc = accuracy_score(y_clean, preds)
        
        high_conf_buy = probs >= self.confidence_threshold
        high_conf_sell = probs <= (1.0 - self.confidence_threshold)
        
        total_buy = np.sum(high_conf_buy)
        total_sell = np.sum(high_conf_sell)
        
        logger.info("=== ENSEMBLE MODEL EVALUATION ===")
        logger.info(f"Base Ensemble Accuracy: {acc:.2%}")
        
        if total_buy > 0:
            buy_prec = precision_score(y_clean[high_conf_buy], np.ones(total_buy), zero_division=0)
            logger.info(f"Filtered BUY Precision (P >= {self.confidence_threshold:.0%}): {buy_prec:.2%} (Total Signals: {total_buy})")
        else:
            logger.info(f"Filtered BUY Precision (P >= {self.confidence_threshold:.0%}): N/A (0 signals)")
            
        if total_sell > 0:
            sell_prec = accuracy_score(y_clean[high_conf_sell], np.zeros(total_sell))
            logger.info(f"Filtered SELL Precision (P <= {1-self.confidence_threshold:.0%}): {sell_prec:.2%} (Total Signals: {total_sell})")
        else:
            logger.info(f"Filtered SELL Precision (P <= {1-self.confidence_threshold:.0%}): N/A (0 signals)")
        logger.info("=================================")
        
        return acc

    def tune_hyperparameters(self, X, y):
        """
        Runs RandomizedSearchCV to find optimal hyperparameters for Random Forest and GBDT.
        Locks in the best parameters on this model instance.
        """
        from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
        from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
        from security import logger
        from sklearn.calibration import CalibratedClassifierCV
        
        logger.info("Initializing hyperparameter auto-tuning on pooled training data...")
        
        valid_idx = X.notna().all(axis=1) & y.notna()
        X_clean = X[valid_idx]
        y_clean = y[valid_idx]
        
        if len(y_clean) < 100:
            logger.warning("Insufficient training samples to run hyperparameter tuning. Keeping default parameters.")
            return
            
        # Ensure feature pruning runs first if it hasn't yet
        if not self.active_features_pruned:
            self.active_features = self.prune_features(X_clean, y_clean)
            self.active_features_pruned = True
            
        X_clean_pruned = X_clean[self.active_features]
        
        # Chronological cross-validation to prevent leakage
        tscv = TimeSeriesSplit(n_splits=3)
        
        # 1. Tune Random Forest
        rf_grid = {
            'n_estimators': [50, 100, 150, 200],
            'max_depth': [3, 5, 7, 10],
            'min_samples_split': [5, 10, 15, 20]
        }
        logger.info("Tuning Random Forest parameters...")
        rf_search = RandomizedSearchCV(
            estimator=RandomForestClassifier(random_state=42, class_weight="balanced"),
            param_distributions=rf_grid,
            n_iter=10,
            scoring='roc_auc',
            cv=tscv,
            random_state=42,
            n_jobs=-1
        )
        try:
            rf_search.fit(X_clean_pruned, y_clean)
            self.rf_model = CalibratedClassifierCV(estimator=rf_search.best_estimator_, method='sigmoid', cv=3)
            logger.info(f"RF Auto-Tuning Complete. Best Params: {rf_search.best_params_}")
        except Exception as e:
            logger.error(f"Random Forest tuning failed: {e}. Keeping default RF model.")
            
        # 2. Tune Gradient Boosting
        gb_grid = {
            'n_estimators': [50, 100, 150],
            'max_depth': [2, 3, 5, 7],
            'learning_rate': [0.01, 0.05, 0.1, 0.2]
        }
        logger.info("Tuning Gradient Boosting parameters...")
        gb_search = RandomizedSearchCV(
            estimator=GradientBoostingClassifier(random_state=42),
            param_distributions=gb_grid,
            n_iter=10,
            scoring='roc_auc',
            cv=tscv,
            random_state=42,
            n_jobs=-1
        )
        try:
            gb_search.fit(X_clean_pruned, y_clean)
            self.gb_model = CalibratedClassifierCV(estimator=gb_search.best_estimator_, method='sigmoid', cv=3)
            logger.info(f"GBDT Auto-Tuning Complete. Best Params: {gb_search.best_params_}")
        except Exception as e:
            logger.error(f"Gradient Boosting tuning failed: {e}. Keeping default GBDT model.")
            
        # 3. Optional: Tune CatBoost if available
        if self.cb_available:
            try:
                from catboost import CatBoostClassifier
                cb_grid = {
                    'depth': [4, 6, 8],
                    'learning_rate': [0.01, 0.05, 0.1],
                    'iterations': [50, 100, 150]
                }
                logger.info("Tuning CatBoost parameters...")
                cb_search = RandomizedSearchCV(
                    estimator=CatBoostClassifier(verbose=0, random_seed=42),
                    param_distributions=cb_grid,
                    n_iter=5,
                    scoring='roc_auc',
                    cv=tscv,
                    random_state=42,
                    n_jobs=-1
                )
                cb_search.fit(X_clean_pruned, y_clean)
                self.cb_model = CalibratedClassifierCV(estimator=cb_search.best_estimator_, method='sigmoid', cv=3)
                logger.info(f"CatBoost Auto-Tuning Complete. Best Params: {cb_search.best_params_}")
            except Exception as e:
                logger.error(f"CatBoost tuning failed: {e}. Keeping default CatBoost model.")

