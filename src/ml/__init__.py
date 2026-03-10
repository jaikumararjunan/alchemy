"""
ML package for Alchemy trading bot.
Provides data science, machine learning, and AI signal augmentation.
"""
from .feature_engineer import FeatureEngineer, FeatureVector, FEATURE_NAMES
from .price_predictor import PricePredictor, PredictionResult
from .sentiment_analyzer import SentimentAnalyzer, SentimentAnalysis
from .anomaly_detector import AnomalyDetector, AnomalyReport, Anomaly
from .signal_classifier import SignalClassifier, SignalDecision
from .model_trainer import MLEngine, MLAnalysis

__all__ = [
    "FeatureEngineer", "FeatureVector", "FEATURE_NAMES",
    "PricePredictor", "PredictionResult",
    "SentimentAnalyzer", "SentimentAnalysis",
    "AnomalyDetector", "AnomalyReport", "Anomaly",
    "SignalClassifier", "SignalDecision",
    "MLEngine", "MLAnalysis",
]
