# train_leaf_model.py -- EfficientNet-B0 transfer learning for leaf image diagnosis
"""
Fine-tunes EfficientNet-B0 on leaf images using PyTorch & torchvision.
Features:
  - Automatic class discovery from dataset directory (data/leaf_images/<class_name>/*.jpg)
  - Preprocessing: Resize to 224x224, ImageNet normalization, data augmentation
  - Two-stage training: Head fine-tuning first, followed by optional unfreezing
  - Supports `--max-per-class` for lightweight CPU training
  - Saves models/leaf_model.pt, models/leaf_effnet_b0.pt, models/leaf_classes.json, and models/leaf_metrics.json

Google Colab Quickstart:
  1. Upload your dataset zip: `data/leaf_images.zip` and unzip:
     `!unzip -q leaf_images.zip -d data/`
  2. Install dependencies:
     `!pip install torch torchvision`
  3. Run GPU training:
     `!python train_leaf_model.py --data data/leaf_images --epochs 15 --batch-size 32`
  4. Download generated artifacts from `models/` into your local `models/` directory.
"""

import os
import sys
import json
import argparse
from typing import List, Tuple
import numpy as np

try:
    # pyrefly: ignore[missing-import]
    import torch
    # pyrefly: ignore[missing-import]
    import torch.nn as nn
    # pyrefly: ignore[missing-import]
    from torch.utils.data import DataLoader, Subset, random_split
    # pyrefly: ignore[missing-import]
    from torchvision import datasets, models, transforms
    from sklearn.metrics import classification_report
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def parse_args():
    parser = argparse.ArgumentParser(description="Train EfficientNet-B0 on crop leaf dataset")
    parser.add_argument("--data", type=str, default="data/leaf_images", help="Path to leaf dataset root folder")
    parser.add_argument("--epochs", type=int, default=12, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=16, help="Training batch size")
    parser.add_argument("--lr", type=float, default=1e-3, help="Initial learning rate")
    parser.add_argument("--max-per-class", type=int, default=None, help="Max images per class for fast CPU training")
    return parser.parse_args()


def get_data_transforms():
    train_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomRotation(degrees=20),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.15),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])

    val_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])

    return train_transform, val_transform


def limit_dataset_per_class(dataset, max_per_class: int):
    """Subsamples dataset to have at most max_per_class items per class."""
    class_indices = {}
    for idx, (_, class_id) in enumerate(dataset.samples):
        class_indices.setdefault(class_id, []).append(idx)

    selected_indices = []
    rng = np.random.RandomState(42)
    for c_id, idxs in class_indices.items():
        if len(idxs) > max_per_class:
            chosen = rng.choice(idxs, size=max_per_class, replace=False).tolist()
        else:
            chosen = idxs
        selected_indices.extend(chosen)

    return Subset(dataset, selected_indices)


def train_model():
    if not HAS_TORCH:
        print("PyTorch or torchvision is not installed in the current environment.")
        print("Please install them via: pip install torch torchvision")
        sys.exit(1)

    args = parse_args()
    os.makedirs("models", exist_ok=True)

    data_dir = args.data
    if not os.path.exists(data_dir):
        # Check alternative folder
        if os.path.exists("data/leaf"):
            data_dir = "data/leaf"
        else:
            print(f"Warning: Dataset directory '{data_dir}' not found.")
            print("Please create data/leaf_images/<class_name>/ with sample images.")
            print("Writing dummy class metadata for development fallback.")
            default_classes = [
                "cotton_nitrogen",
                "cotton_lalya",
                "tomato_early_blight",
                "tomato_leaf_curl",
                "soybean_mosaic",
                "healthy_leaf",
            ]
            with open("models/leaf_classes.json", "w", encoding="utf-8") as f:
                json.dump(default_classes, f, indent=2)
            return

    train_tf, val_tf = get_data_transforms()
    full_dataset = datasets.ImageFolder(data_dir, transform=train_tf)
    classes = full_dataset.classes
    print(f"Discovered {len(classes)} leaf disease classes: {classes}")

    if args.max_per_class:
        full_dataset = limit_dataset_per_class(full_dataset, args.max_per_class)
        print(f"Subsampled dataset to maximum {args.max_per_class} images per class. Total samples: {len(full_dataset)}")

    n_val = max(1, int(0.2 * len(full_dataset)))
    n_train = len(full_dataset) - n_val
    train_ds, val_ds = random_split(full_dataset, [n_train, n_val], generator=torch.Generator().manual_seed(42))

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training using compute device: {device}")

    # Load pretrained EfficientNet-B0
    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT)

    # Stage 1: Freeze feature backbone and train classification head
    for param in model.features.parameters():
        param.requires_grad = False

    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Sequential(
        nn.Dropout(p=0.3, inplace=True),
        nn.Linear(in_features, len(classes))
    )
    model.to(device)

    criterion = nn.CrossEntropyLoss()
    best_val_acc = 0.0
    best_report = {}

    def run_epoch(dataloader, optimizer=None):
        is_train = optimizer is not None
        model.train(is_train)
        total_loss, total_correct, total_samples = 0.0, 0, 0
        all_preds, all_labels = [], []

        for x, y in dataloader:
            x, y = x.to(device), y.to(device)
            with torch.set_grad_enabled(is_train):
                outputs = model(x)
                loss = criterion(outputs, y)
                if is_train:
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()

            preds = outputs.argmax(dim=1)
            total_loss += loss.item() * len(y)
            total_correct += (preds == y).sum().item()
            total_samples += len(y)
            if not is_train:
                all_preds.extend(preds.cpu().numpy().tolist())
                all_labels.extend(y.cpu().numpy().tolist())

        acc = total_correct / max(1, total_samples)
        return acc, all_labels, all_preds

    # Two-stage fine tuning: Head first, then top blocks
    stages = [(args.lr, False, max(1, args.epochs // 2)), (args.lr * 0.1, True, max(1, args.epochs // 2))]

    for stage_idx, (lr, unfreeze_backbone, stage_epochs) in enumerate(stages):
        if unfreeze_backbone:
            print("\nStage 2: Unfreezing top blocks of EfficientNet backbone for fine-tuning...")
            for param in model.features[-2:].parameters():
                param.requires_grad = True

        optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=lr, weight_decay=1e-4)

        for epoch in range(stage_epochs):
            train_acc, _, _ = run_epoch(train_loader, optimizer)
            val_acc, val_labels, val_preds = run_epoch(val_loader, None)
            print(f"Stage {stage_idx + 1} | Epoch {epoch + 1}/{stage_epochs} | Train Acc: {train_acc:.3f} | Val Acc: {val_acc:.3f}")

            if val_acc >= best_val_acc:
                best_val_acc = val_acc
                torch.save(model.state_dict(), "models/leaf_model.pt")
                torch.save(model.state_dict(), "models/leaf_effnet_b0.pt")
                with open("models/leaf_classes.json", "w", encoding="utf-8") as f:
                    json.dump(classes, f, indent=2)

                if val_labels and val_preds:
                    best_report = classification_report(
                        val_labels, val_preds, target_names=[classes[i] for i in sorted(list(set(val_labels)))],
                        output_dict=True, zero_division=0
                    )

    metrics_payload = {
        "architecture": "EfficientNet-B0",
        "best_val_accuracy": round(float(best_val_acc), 4),
        "classes": classes,
        "n_samples": len(full_dataset),
        "classification_report": best_report,
    }
    with open("models/leaf_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2)

    print(f"\nTraining complete. Best Validation Accuracy: {best_val_acc:.3f}")
    print("Saved model artifacts to models/leaf_model.pt and models/leaf_classes.json")


if __name__ == "__main__":
    train_model()
