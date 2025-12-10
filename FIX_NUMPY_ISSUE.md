# Исправление проблемы с numpy/pandas

## Проблема
```
numpy.dtype size changed, may indicate binary incompatibility. Expected 96 from C header, got 88 from PyObject
```

Это происходит из-за несовместимости версий numpy и pandas.

## Решение

### Вариант 1: Переустановка зависимостей (рекомендуется)

```bash
pip uninstall numpy pandas scikit-learn sentence-transformers -y
pip install numpy==1.24.3 pandas==2.0.3 scikit-learn==1.3.0 sentence-transformers
```

### Вариант 2: Обновление всех зависимостей

```bash
pip install --upgrade numpy pandas scikit-learn sentence-transformers
```

### Вариант 3: Переустановка всех зависимостей из requirements.txt

```bash
pip uninstall -r requirements.txt -y
pip install -r requirements.txt
```

## После исправления

После переустановки запустите бота снова:
```bash
python run_bot.py
```

IntentRecognizer и RAG должны заработать.

