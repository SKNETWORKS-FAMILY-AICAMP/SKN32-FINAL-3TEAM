from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

model_dir = r'docs\psj\e2e_prototype\copylane-encoder-koelectra-final'
tokenizer = AutoTokenizer.from_pretrained(model_dir)
model = AutoModelForSequenceClassification.from_pretrained(model_dir)
model.eval()

texts = ['맛있게 즐기실 수 있는 건강한 간식입니다', '이 제품을 드시면 당뇨가 완치됩니다']
for text in texts:
    inputs = tokenizer(text, truncation=True, max_length=128, padding='max_length', return_tensors='pt')
    print(text)
    print('input_ids[:20]:', inputs['input_ids'][0][:20].tolist())
    print('attention_mask sum:', inputs['attention_mask'].sum().item())
    with torch.no_grad():
        logits = model(**inputs).logits
    print('logits:', logits[0].tolist())
    print('probs:', torch.sigmoid(logits)[0].tolist())
    print()
