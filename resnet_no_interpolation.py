import os
import csv
import pandas as pd
import torch
from torchvision import transforms
from torch.utils.data import Dataset, ConcatDataset, DataLoader
from torchvision.models import resnet50
from PIL import Image
import torch.nn as nn

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

classes = ('benign', 'malignant', 'normal')

n_epochs = 300
batch_size = 32
img_size = 256
n_classes = len(classes)
lr = 0.001
beta_1 = 0.5
beta_2 = 0.999

directory = os.getcwd()

img_dir_original = os.path.join(directory, 'BUSI/split/train')
label_dir_original = os.path.join(directory, 'BUSI/split/labels_train.csv')

img_dir_generated = os.path.join(directory, 'gen_dataset/no_interpolation')
label_dir_generated = os.path.join(directory, 'gen_dataset/no_interpolation_labels.csv')

img_dir_test = os.path.join(directory, 'BUSI/split/test/original')
label_dir_test = os.path.join(directory, 'BUSI/split/labels_test.csv')


class CustomDataset(Dataset):
    def __init__(self, img_dir, label_dir, transform=None):
        self.img_dir = img_dir
        self.label_dir = label_dir
        self.transform = transform

        self.labels_df = pd.read_csv(label_dir, header=None)

    def __len__(self):
        return len(self.labels_df)

    def __getitem__(self, index):
        filename = self.labels_df.iloc[index, 0]
        label = self.labels_df.iloc[index, 1]

        label = [float(i) for i in label.split(',')]
        label = torch.tensor(label)

        image_path = os.path.join(self.img_dir, filename)

        image = self.load_image(image_path)

        if self.transform:
            image = self.transform(image)

        return image, label

    def load_image(self, image_path):
        image = Image.open(image_path).convert('RGB')
        return image


transform = transforms.Compose([
    transforms.transforms.Resize((img_size, img_size), interpolation=transforms.InterpolationMode.BILINEAR),
    transforms.ToTensor(),
    transforms.Normalize([0.5], [0.5])])

original_dataset = CustomDataset(img_dir_original, label_dir_original, transform=transform)
generated_dataset = CustomDataset(img_dir_generated, label_dir_generated, transform=transform)

combined_dataset = ConcatDataset([original_dataset, generated_dataset])
combined_loader = DataLoader(combined_dataset, batch_size=batch_size, shuffle=True)

test_dataset = CustomDataset(img_dir_test, label_dir_test, transform=transform)
test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=True)

model = resnet50(pretrained=False)
model.fc = nn.Linear(2048, 3)

if torch.cuda.is_available():
    model.cuda()

criterion = nn.CrossEntropyLoss().to(device)
optimizer = torch.optim.Adam(model.parameters(), lr, betas=(beta_1, beta_2))

stats = []
highest_test_accuracy = 0.0

for epoch in range(n_epochs):
    running_train_loss = 0.0
    running_train_accuracy = 0.0
    running_test_accuracy = 0.0
    total_train = 0
    total_test = 0

    for i, (images, labels) in enumerate(combined_loader):
        model.train()
        optimizer.zero_grad()

        current_batch_size = images.size()[0]

        images = images.to(device)
        labels = labels.to(device)

        output = model(images.float())
        train_loss = criterion(output, labels)

        _, predicted = torch.max(output, 1)
        _, label = torch.max(labels, 1)

        train_loss.backward()
        optimizer.step()

        total_train += current_batch_size
        running_train_loss += train_loss.item()
        running_train_accuracy += (predicted == label).sum().item()

    with torch.no_grad():
        model.eval()
        for i, (images, labels) in enumerate(test_loader):
            current_batch_size = images.size()[0]

            images = images.to(device)
            labels = labels.to(device)

            output = model(images.float())
            test_loss = criterion(output, labels)

            _, predicted = torch.max(output, 1)
            _, label = torch.max(labels, 1)

            total_test += current_batch_size
            running_test_accuracy += (predicted == label).sum().item()

    train_loss_epoch = running_train_loss / total_train
    train_accuracy = 100 * running_train_accuracy / total_train
    test_accuracy = 100 * running_test_accuracy / total_test

    stats_epoch = {
        'epoch': f'{epoch + 1}',
        'train loss': f'{train_loss_epoch:.3f}',
        'train accuracy': f'{train_accuracy:.2f}%',
        'test accuracy': f'{test_accuracy:.2f}%'
    }

    stats.append(stats_epoch)

    fieldnames = ['epoch', 'train loss', 'train accuracy', 'test accuracy']

    with open('stats_no_interpolation.csv', 'w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for parameter in stats:
            writer.writerow(parameter)

    if test_accuracy > highest_test_accuracy and epoch > 50:
        highest_test_accuracy = test_accuracy
        torch.save(model.state_dict(), 'checkpoints_no_interpolation/checkpoint epoch {}.pt'.format(epoch + 1))

    elif (epoch + 1) % 50 == 0:
        torch.save(model.state_dict(), 'checkpoints_no_interpolation/checkpoint epoch {}.pt'.format(epoch + 1))