"""The two permitted ResNet-50 model variants."""

from __future__ import annotations

import torch
from torch import nn
from torchvision.models import ResNet50_Weights, resnet50


class ActionOnlyModel(nn.Module):
    def __init__(self, pretrained: bool = True) -> None:
        super().__init__()
        weights = ResNet50_Weights.DEFAULT if pretrained else None
        network = resnet50(weights=weights)
        feature_dim = network.fc.in_features
        network.fc = nn.Identity()
        self.backbone = network
        self.action_head = nn.Linear(feature_dim, 4)

    def forward(self, images: torch.Tensor) -> dict[str, torch.Tensor]:
        features = self.backbone(images)
        return {"action_logits": self.action_head(features)}


class JointActionRationaleModel(nn.Module):
    def __init__(self, pretrained: bool = True) -> None:
        super().__init__()
        weights = ResNet50_Weights.DEFAULT if pretrained else None
        network = resnet50(weights=weights)
        feature_dim = network.fc.in_features
        network.fc = nn.Identity()
        self.backbone = network
        self.action_head = nn.Linear(feature_dim, 4)
        self.rationale_head = nn.Linear(feature_dim, 21)

    def forward(self, images: torch.Tensor) -> dict[str, torch.Tensor]:
        features = self.backbone(images)
        return {
            "action_logits": self.action_head(features),
            "rationale_logits": self.rationale_head(features),
        }


def build_model(model_type: str, pretrained: bool = True) -> nn.Module:
    if model_type == "action_only":
        return ActionOnlyModel(pretrained=pretrained)
    if model_type == "joint":
        return JointActionRationaleModel(pretrained=pretrained)
    raise ValueError(f"Unknown model type: {model_type}")


def load_checkpoint_model(
    checkpoint_path: str,
    model_type: str,
    device: torch.device,
) -> nn.Module:
    checkpoint = torch.load(
        checkpoint_path, map_location=device, weights_only=False
    )
    model = build_model(model_type, pretrained=False)
    model.load_state_dict(checkpoint["model_state"])
    return model.to(device).eval()

