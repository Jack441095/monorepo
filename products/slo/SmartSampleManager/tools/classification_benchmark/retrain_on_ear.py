import csv, numpy as np
import drum_detector_features as ddf
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_predict
from collections import Counter

rows=[r for r in csv.DictReader(open('verified_drums.csv')) if r['label']!='__skip__']
VIABLE=['Kick','Snare','Hi-Hat','Clap','Other/none']  # >=57 examples each
tr=[r for r in rows if r['label'] in VIABLE]
print(f"training on {len(tr)} by-ear labels across {len(VIABLE)} viable classes")
print("thin classes held out (too few to learn): Crash 16, Foley 9, Rimshot 8, Percussion 7, Loop 7\n")

X,y,paths=[],[],[]
for r in tr:
    f=ddf.extract(r['path'])
    if f is not None: X.append(f); y.append(r['label']); paths.append(r['path'])
X=np.array(X); y=np.array(y); paths=np.array(paths)

clf=RandomForestClassifier(n_estimators=300,class_weight='balanced',random_state=0)
proba=cross_val_predict(clf,X,y,cv=5,method='predict_proba')
classes=sorted(set(y)); ci={c:i for i,c in enumerate(classes)}
# align proba columns
clf.fit(X,y); cls=list(clf.classes_)
proba=cross_val_predict(clf,X,y,cv=5,method='predict_proba')
pred=np.array(cls)[proba.argmax(1)]; conf=proba.max(1)

print("REAL accuracy vs your ear (5-fold CV):")
print(f"  overall: {100*(pred==y).mean():.1f}%\n")
from sklearn.metrics import classification_report
print(classification_report(y,pred,digits=3))
print("\nConfidence-gated (for auto-rename):")
for t in [0.5,0.7,0.8,0.9]:
    m=conf>=t
    if m.sum(): print(f"  >={t}: rename {100*m.mean():.0f}% of files at {100*(pred[m]==y[m]).mean():.1f}% precision")

# REVIEW QUEUE: detector confident but disagrees with your label -> likely mislabel or ambiguous
dis=(pred!=y)&(conf>=0.75)
import os
print(f"\n=== REVIEW QUEUE: {int(dis.sum())} files where the detector is confident but disagrees with your label ===")
print("(these are the 'few to review' -- either a slip, or genuinely ambiguous)")
with open('review_queue.csv','w',newline='') as f:
    w=csv.writer(f); w.writerow(['your_label','detector_says','confidence','file'])
    for i in np.where(dis)[0]:
        w.writerow([y[i],pred[i],round(float(conf[i]),2),paths[i]])
        print(f"  you:{y[i]:>10}  detector:{pred[i]:>10} ({conf[i]:.2f})  {os.path.basename(paths[i])[:50]}")
print("\nsaved review_queue.csv")
