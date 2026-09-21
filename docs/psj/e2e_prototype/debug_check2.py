from transformers import AutoModelForSequenceClassification
import torch

model_dir = r'docs\psj\e2e_prototype\copylane-encoder-koelectra-final'
model = AutoModelForSequenceClassification.from_pretrained(model_dir)

# backbone 첫 레이어 가중치 확인
for name, param in list(model.electra.named_parameters())[:5]:
    print(name, param.shape, 'mean=', param.data.mean().item(), 'std=', param.data.std().item())

print()
# 사전학습 원본(monologg/koelectra-base-v3-discriminator)과 비교
base_model = AutoModelForSequenceClassification.from_pretrained(
    'monologg/koelectra-base-v3-discriminator', num_labels=8, problem_type='multi_label_classification'
)
for (name1, p1), (name2, p2) in zip(model.electra.named_parameters(), base_model.electra.named_parameters()):
    same = torch.allclose(p1.data, p2.data)
    if same:
        print('동일함(=파인튜닝 안 됨 의심):', name1)
