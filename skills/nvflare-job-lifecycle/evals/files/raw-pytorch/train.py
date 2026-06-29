import torch


def train_one_step(model, batch):
    loss = model(batch).sum()
    loss.backward()
    return float(loss.detach())
