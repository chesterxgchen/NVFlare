import torch


def train_one_epoch(model, loader, optimizer, loss_fn):
    model.train()
    for features, labels in loader:
        optimizer.zero_grad()
        loss = loss_fn(model(features), labels)
        loss.backward()
        optimizer.step()
