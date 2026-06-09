from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os, io, numpy as np

ESCUDOS_DIR = os.path.join(os.path.dirname(__file__), "escudos")

ESCUDOS_MAP = {
    "atletico nacional": "Atletico_Nacional.png",
    "america de cali": "America_de_Cali.jpg",
    "deportivo cali": "Deportivo_Cali.jpg",
    "millonarios": "Millonarios.png",
    "deportes tolima": "Deportes_Tolima.png",
    "junior fc": "Junior_FC.png",
    "dim": "DIM.jpg",
    "atletico bucaramanga": "Atletico_Bucaramanga.png",
    "santa fe": "Santa_Fe.png",
    "once caldas": "Once_Caldas.png",
    "deportivo pasto": "Deportivo_Pasto.png",
    "alianza fc": "Alianza_FC.png",
}

def remove_bg_flood(img, tolerance=30):
    img = img.convert("RGBA")
    data = np.array(img, dtype=np.uint8)
    h, w = data.shape[:2]
    visited = np.zeros((h, w), dtype=bool)
    mask = np.zeros((h, w), dtype=bool)
    def similar(c1, c2):
        return all(abs(int(c1[i])-int(c2[i])) <= tolerance for i in range(3))
    from collections import deque
    for sy, sx in [(0,0),(0,w-1),(h-1,0),(h-1,w-1)]:
        if visited[sy,sx]: continue
        bg = data[sy,sx]
        q = deque([(sy,sx)])
        visited[sy,sx] = True
        while q:
            y, x = q.popleft()
            if similar(data[y,x], bg):
                mask[y,x] = True
                for dy,dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                    ny,nx = y+dy,x+dx
                    if 0<=ny<h and 0<=nx<w and not visited[ny,nx]:
                        visited[ny,nx] = True
                        q.append((ny,nx))
    data[mask,3] = 0
    return Image.fromarray(data)

def get_escudo(nombre):
    key = nombre.lower().strip()
    filename = ESCUDOS_MAP.get(key)
    if not filename:
        for k,v in ESCUDOS_MAP.items():
            if k in key or key in k:
                filename = v
                break
    if not filename: return None
    path = os.path.join(ESCUDOS_DIR, filename)
    if not os.path.exists(path): return None
    return remove_bg_flood(Image.open(path).convert("RGBA"))

def pegar(img, esc, cx, cy, size=115):
    if not esc: return
    e = esc.copy()
    e.thumbnail((size,size), Image.LANCZOS)
    img.paste(e, (cx-e.width//2, cy-e.height//2), e)

def flechas(draw, cx, cy, color=(255,190,0)):
    aw, ah, gap = 26, 42, 12
    for off in [-aw-gap//2, gap//2]:
        x = cx+off
        pts = [(x,cy-ah//2),(x+aw,cy),(x,cy+ah//2),(x+9,cy+ah//2),(x+aw+9,cy),(x+9,cy-ah//2)]
        draw.polygon(pts, fill=color)
        draw.polygon(pts, outline=(0,0,0,160), width=2)

def generar_fichaje(nombre_jugador, posicion, dorsal, equipo_origen, equipo_destino, monto=None):
    W, H = 720, 580
    img = Image.new("RGBA", (W,H), (0,0,0,255))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        v = int(8+(y/H)*20)
        draw.line([(0,y),(W,y)], fill=(v,v,v+10,255))
    logo_path = os.path.join(ESCUDOS_DIR, "logo_glare.png")
    if os.path.exists(logo_path):
        lb = Image.open(logo_path).convert("RGBA").resize((460,460), Image.LANCZOS)
        lb = lb.filter(ImageFilter.GaussianBlur(7))
        r,g,b,a = lb.split()
        lb.putalpha(a.point(lambda x: int(x*0.15)))
        img.paste(lb, ((W-lb.width)//2,(H-lb.height)//2), lb)
    draw.rectangle([(0,0),(7,H)], fill=(255,190,0,255))
    draw.rectangle([(W-7,0),(W,H)], fill=(255,190,0,255))
    try:
        ft = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        fn = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        fs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
        fd = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 84)
        fm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        fc = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except:
        ft=fn=fs=fd=fm=fc=ImageFont.load_default()
    draw.rectangle([(0,0),(W,62)], fill=(10,10,10,235))
    draw.rectangle([(0,60),(W,66)], fill=(255,190,0,255))
    if os.path.exists(logo_path):
        ls = Image.open(logo_path).convert("RGBA")
        ls.thumbnail((48,48), Image.LANCZOS)
        img.paste(ls,(14,7),ls)
    draw.text((W//2+20,31), "FICHAJE OFICIAL", font=ft, fill=(255,255,255), anchor="mm")
    cx, cyd = W//2, 190
    r = 85
    draw.ellipse([(cx-r+5,cyd-r+5),(cx+r+5,cyd+r+5)], fill=(0,0,0,140))
    draw.ellipse([(cx-r,cyd-r),(cx+r,cyd+r)], fill=(175,20,20,250))
    draw.ellipse([(cx-r,cyd-r),(cx+r,cyd+r)], outline=(255,190,0,255), width=5)
    draw.text((cx,cyd), str(dorsal), font=fd, fill=(255,255,255), anchor="mm")
    cye = 365
    exo, exd = 155, W-155
    pegar(img, get_escudo(equipo_origen), exo, cye)
    pegar(img, get_escudo(equipo_destino), exd, cye)
    flechas(draw, W//2, cye)
    draw.text((exo,cye+78), equipo_origen.upper()[:16], font=fc, fill=(170,170,170), anchor="mm")
    draw.text((exd,cye+78), equipo_destino.upper()[:16], font=fc, fill=(255,255,255), anchor="mm")
    draw.rectangle([(30,468),(W-30,471)], fill=(255,190,0,180))
    draw.text((W//2,492), nombre_jugador.upper(), font=fn, fill=(255,255,255), anchor="mm")
    draw.text((W//2,520), posicion, font=fs, fill=(150,150,150), anchor="mm")
    if monto:
        ms = f"VALOR: ${monto:,}".replace(",",".")
        draw.rectangle([(W//2-130,542),(W//2+130,566)], fill=(255,190,0,220))
        draw.text((W//2,554), ms, font=fm, fill=(0,0,0), anchor="mm")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf
