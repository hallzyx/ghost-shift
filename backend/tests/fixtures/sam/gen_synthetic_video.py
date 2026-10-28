"""Genera synthetic.mp4 + ground_truth.json (fixture T0). Uso: python gen_synthetic_video.py synthetic.mp4"""
import numpy as np, subprocess, json, sys
W,H,FPS,DUR=640,360,10,8
S=60
BLUE=(30,60,220); YEL=(240,210,20); SKIN=(224,172,140); BG=(235,235,230)
def lerp(a,b,t): return a+(b-a)*min(max(t,0),1)
def posA(t):  # entra por izquierda a 1s, llega a x=160 en 1.8s
    if t<1.0: return None
    return (lerp(-S,160,(t-1.0)/0.8), 150)
def posB(t):
    if t<4.0: return None
    return (lerp(W,480,(t-4.0)/0.8), 150)
HAND=(6.0,7.0)  # mano tapa A
def hand(t):
    if not(HAND[0]-0.3<=t<=HAND[1]+0.3): return None
    # rect 110x110 centrado sobre A, entra desde arriba y sale
    a=min(1,(t-(HAND[0]-0.3))/0.3); b=min(1,((HAND[1]+0.3)-t)/0.3)
    k=min(a,b)
    return (160-25, lerp(-120,150-25,k), 110,110)
gt=[]
cmd=['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
     '-c:v','libx264','-pix_fmt','yuv420p','-crf','18',sys.argv[1]]
p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
for f in range(FPS*DUR):
    t=f/FPS
    img=np.zeros((H,W,3),np.uint8); img[:]=BG
    rec={'f':f,'t':t}
    for name,pos,col in (('A',posA,BLUE),('B',posB,YEL)):
        q=pos(t)
        if q:
            x,y=int(round(q[0])),int(round(q[1]))
            x0,x1=max(x,0),min(x+S,W)
            if x1>x0:
                img[y:y+S,x0:x1]=col
                rec[name]=[x0,y,x1,y+S]
    h=hand(t)
    if h:
        x,y,w,hh=map(int,h); y0=max(y,0)
        img[y0:y+hh,x:x+w]=SKIN; rec['hand']=[x,y0,x+w,min(y+hh,H)]
    gt.append(rec)
    p.stdin.write(img.tobytes())
p.stdin.close(); p.wait()
json.dump({'w':W,'h':H,'fps':FPS,'frames':gt},open('ground_truth.json','w'))
