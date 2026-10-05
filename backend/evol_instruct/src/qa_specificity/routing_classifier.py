"""
Routing Classifier — Inference Wrapper
=======================================
Load adapter PhoBERT đã fine-tune để phân loại câu hỏi pháp lý:
    - "broad"  → câu hỏi tổng quát, top-K lớn + graph expansion mạnh
    - "narrow" → câu hỏi cụ thể, top-K nhỏ, precision-focused

Sử dụng trong QueryEvolver:
    classifier = RoutingClassifier(model_dir="backend/models/routing_classifier")
    label = classifier.predict("Điều kiện để được bồi thường thiệt hại là gì?")
    # → "narrow"

Nếu adapter chưa được train (chưa chạy script 13), tự động fallback
về heuristic đơn giản dựa trên độ dài câu hỏi.
"""

import json
import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

SpecificityLabel = Literal["broad", "narrow"]

# PhoBERT được pre-train trên văn bản ĐÃ tách từ (âm tiết nối bằng "_"). Đưa câu
# thô vào thì "khởi kiện" thành hai token rời và dấu câu dính vào chữ ("đồng,"
# → "đồ@@ ng@@ ,"). Train và inference PHẢI dùng cùng một hàm này — lệch nhau là
# model nhận phân phối input khác hẳn lúc học.
SEGMENTER_NAME = "underthesea.word_tokenize"


def segment_vi(text: str) -> str:
    """Tách từ tiếng Việt theo định dạng PhoBERT cần ("khởi_kiện")."""
    from underthesea import word_tokenize
    return word_tokenize(text, format="text")


class RoutingClassifier:
    """
    Singleton-friendly wrapper cho PhoBERT + LoRA adapter.
    Thread-safe để dùng trong FastAPI (một instance dùng chung).
    """

    def __init__(self, model_dir: str | Path):
        self.model_dir = Path(model_dir)
        self._model = None
        self._tokenizer = None
        self._label2id: dict = {"broad": 0, "narrow": 1}
        self._id2label: dict = {0: "broad", 1: "narrow"}
        self._max_length: int = 256
        self._segment: bool = True
        self._ready: bool = False
        self._fallback_mode: bool = False

        self._load()

    # ─── Khởi tạo ─────────────────────────────────────────────────────────────
    def _load(self):
        config_path = self.model_dir / "train_config.json"

        if not self.model_dir.exists() or not config_path.exists():
            logger.warning(
                f"[RoutingClassifier] Không tìm thấy adapter tại: {self.model_dir}\n"
                "  → Chạy script 13_train_routing_classifier.py trước.\n"
                "  → Tạm thời dùng heuristic fallback (word count)."
            )
            self._fallback_mode = True
            return

        try:
            # Đọc config được lưu lúc train
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            self._max_length = cfg.get("max_length", 256)
            self._label2id = cfg.get("label2id", self._label2id)
            # id2label có thể có key là string (JSON serialize)
            raw_id2label = cfg.get("id2label", {})
            self._id2label = {int(k): v for k, v in raw_id2label.items()}
            # Adapter train trước khi có bước tách từ thì không có khoá này.
            self._segment = cfg.get("segmenter") is not None

            import torch
            from transformers import AutoTokenizer
            from peft import AutoPeftModelForSequenceClassification

            logger.info(f"[RoutingClassifier] Loading adapter: {self.model_dir}")
            self._tokenizer = AutoTokenizer.from_pretrained(
                str(self.model_dir), use_fast=False
            )

            device = "cuda" if torch.cuda.is_available() else "cpu"
            # num_labels/id2label phải khớp lúc train, nếu không base model dựng
            # head phân loại sai kích thước trước khi nạp trọng số adapter.
            self._model = AutoPeftModelForSequenceClassification.from_pretrained(
                str(self.model_dir),
                num_labels=len(self._id2label),
                id2label=self._id2label,
                label2id=self._label2id,
            ).to(device)
            self._model.eval()
            self._device = device
            self._ready = True

            f1 = cfg.get("val_f1_macro", "N/A")
            logger.info(
                f"[RoutingClassifier] ✅ Sẵn sàng | val_f1_macro={f1} | device={device}"
            )

        except Exception as e:
            logger.error(f"[RoutingClassifier] Lỗi khi load model: {e}")
            logger.warning("  → Fallback về heuristic word count.")
            self._fallback_mode = True

    # ─── Inference ────────────────────────────────────────────────────────────
    def _prep(self, query: str) -> str:
        return segment_vi(query) if self._segment else query

    def predict(self, query: str) -> SpecificityLabel:
        """
        Phân loại một câu hỏi thành 'broad' hoặc 'narrow'.
        Luôn trả về kết quả (không raise exception).
        """
        if self._fallback_mode or not self._ready:
            return self._heuristic_fallback(query)

        try:
            import torch

            inputs = self._tokenizer(
                self._prep(query),
                max_length=self._max_length,
                truncation=True,
                padding=True,
                return_tensors="pt",
            ).to(self._device)

            with torch.no_grad():
                outputs = self._model(**inputs)

            pred_id = int(outputs.logits.argmax(dim=-1).item())
            label = self._id2label.get(pred_id, "broad")
            logger.debug(f"[RoutingClassifier] '{query[:60]}...' → {label}")
            return label

        except Exception as e:
            logger.warning(f"[RoutingClassifier] Predict lỗi: {e} → fallback")
            return self._heuristic_fallback(query)

    def predict_batch(self, queries: list[str]) -> list[SpecificityLabel]:
        """Phân loại nhiều câu hỏi cùng lúc (efficient hơn gọi predict() từng cái)."""
        if self._fallback_mode or not self._ready:
            return [self._heuristic_fallback(q) for q in queries]

        try:
            import torch

            inputs = self._tokenizer(
                [self._prep(q) for q in queries],
                max_length=self._max_length,
                truncation=True,
                padding=True,
                return_tensors="pt",
            ).to(self._device)

            with torch.no_grad():
                outputs = self._model(**inputs)

            pred_ids = outputs.logits.argmax(dim=-1).tolist()
            return [self._id2label.get(pid, "broad") for pid in pred_ids]

        except Exception as e:
            logger.warning(f"[RoutingClassifier] Batch predict lỗi: {e} → fallback")
            return [self._heuristic_fallback(q) for q in queries]

    # ─── Heuristic fallback ───────────────────────────────────────────────────
    @staticmethod
    def _heuristic_fallback(query: str) -> SpecificityLabel:
        """
        Fallback khi chưa có adapter fine-tune.
        Logic đơn giản: câu hỏi ngắn (<= 12 từ) → broad, dài hơn → narrow.
        Dựa trên observation từ dữ liệu QA Specificity.
        """
        word_count = len(query.split())
        label: SpecificityLabel = "narrow" if word_count > 12 else "broad"
        logger.debug(f"[RoutingClassifier][heuristic] words={word_count} → {label}")
        return label

    # ─── Trạng thái ───────────────────────────────────────────────────────────
    @property
    def is_ready(self) -> bool:
        """True nếu adapter đã load thành công."""
        return self._ready

    @property
    def mode(self) -> str:
        return "heuristic" if self._fallback_mode else "phobert-lora"

    def __repr__(self):
        return (
            f"RoutingClassifier(mode={self.mode}, "
            f"ready={self._ready}, dir={self.model_dir})"
        )
