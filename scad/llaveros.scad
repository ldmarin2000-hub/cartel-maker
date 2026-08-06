// ===============================
//   LLAVERO PERSONALIZADO
//   Diseño base: Vanessa Matos
//   + tipografia personalizada, colores, decoracion y aros
// ===============================
// Panel: Window > Customizer

/* [Texto] */
User_Name = "Bianca";
Font_Size = 20;                // [10:1:60]

/* [Tipografia] */
Custom_Font = false;
// Nombre EXACTO (OpenSCAD: Window > Font List). Ej: "Neon Backlight" o "Pacifico"
Custom_Font_Name = "";
Font_Name = "Lily Script One"; // [Aladin, Dancing Script, Pacifico, Courgette, Lobster, Chewy, Lemon, Playfair Display, Cookie, Lily Script One]

/* [Colores (solo vista previa)] */
Base_Color = "White";          // [White, Black, Silver, Gray, Pink, HotPink, DeepPink, Red, Orange, Gold, Yellow, Lime, Green, SkyBlue, Blue, Purple, Violet, Turquoise, SaddleBrown]
Text_Color = "HotPink";        // [White, Black, Silver, Gray, Pink, HotPink, DeepPink, Red, Orange, Gold, Yellow, Lime, Green, SkyBlue, Blue, Purple, Violet, Turquoise, SaddleBrown]

/* [Decoracion] */
Decoracion      = "corazon";   // [ninguno:Ninguno, corazon:Corazon, estrella:Estrella, flor:Flor, gato:Gato, rayo:Rayo, luna:Luna, rombo:Rombo, circulo:Circulo, svg:Imagen SVG propia]
Decoracion_Lado = "derecha";   // [izquierda, derecha, arriba]
Decoracion_Tam  = 7;           // [3:0.5:20]
Deco_X          = 0;           // [-40:0.5:40]  ajuste fino horizontal
Deco_Y          = 0;           // [-40:0.5:40]  ajuste fino vertical
// Para "Imagen SVG propia": ruta del .svg (misma carpeta que el .scad, o ruta completa)
SVG_File        = "dibujo.svg";

/* [Aros] */
Aro_Lado    = "izquierda";     // [izquierda, derecha, ambos, ninguno]
Aro_R       = 2;               // [1:0.25:5]   radio del agujero
Ring_Offset = 0;               // [-15:0.5:15] corrimiento del aro izquierdo
Aro_Ajuste_Der = 0;            // [-30:0.5:30] ajuste del aro derecho

/* [Medidas] */
Text_Height  = 2;              // [1:0.5:6]
Plate_Height = 3;              // [1:0.5:8]
Border_Size  = 3;              // [1:0.5:10]

/* [Exportar] */
// todo = vista previa color · base/texto = una pieza por color (para imprimir 2 colores)
Export_Part = "todo";          // [todo:Vista previa, base:Solo base, texto:Solo texto+deco]
// true = para AMS/multicolor: la pieza de texto NO se corre, queda en su posición real
// (encima de la base) para importar las 2 piezas juntas en Bambu Studio y asignarles
// un color a cada una. false = pieza de texto apoyada en el suelo, para imprimirla sola.
Multicolor_AMS = false;

/* [Hidden] */
$fn = 64;
_font = (Custom_Font && Custom_Font_Name != "") ? Custom_Font_Name : Font_Name;
_w = Font_Size * len(User_Name) * 0.72;   // ancho estimado del texto
_cy = Font_Size/2;

// ===============================
//   2D
// ===============================
module _name2d() text(User_Name, size = Font_Size, font = _font);

function _starpts(n,ro,ri) =
    [ for (i=[0:2*n-1]) let(a = 90 + i*180/n, r = (i%2==0)?ro:ri) [r*cos(a), r*sin(a)] ];
module _star(t)  polygon(_starpts(5, t, t*0.5));
module _heart(t) scale([t/1.4, t/1.4])
    union() {
        translate([-0.5,0]) circle(0.5);
        translate([ 0.5,0]) circle(0.5);
        polygon([[-0.98,0.12],[0.98,0.12],[0,-1.15]]);
    }
module _flor(t)  { for (i=[0:5]) rotate(i*60) translate([t*0.55,0]) circle(t*0.45); circle(t*0.5); }
module _gato(t)  { circle(t*0.8);
    for (m=[-1,1]) scale([m,1]) translate([t*0.5,t*0.5]) polygon([[-t*0.28,0],[t*0.28,0],[0,t*0.55]]); }
module _rayo(t)  scale([t,t]) polygon([[0.15,1],[-0.45,0.05],[-0.05,0.05],[-0.2,-1],[0.5,0.0],[0.1,0.0]]);
module _luna(t)  difference() { circle(t); translate([t*0.55,0]) circle(t*0.92); }
module _rombo(t) polygon([[0,t],[t*0.7,0],[0,-t],[-t*0.7,0]]);
module _forma2d()
         if (Decoracion=="corazon")  _heart(Decoracion_Tam);
    else if (Decoracion=="estrella") _star(Decoracion_Tam);
    else if (Decoracion=="flor")     _flor(Decoracion_Tam);
    else if (Decoracion=="gato")     _gato(Decoracion_Tam);
    else if (Decoracion=="rayo")     _rayo(Decoracion_Tam);
    else if (Decoracion=="luna")     _luna(Decoracion_Tam);
    else if (Decoracion=="rombo")    _rombo(Decoracion_Tam);
    else if (Decoracion=="svg")      resize([0, Decoracion_Tam*2, 0], auto=true)
                                         import(file=SVG_File, center=true);
    else                              circle(Decoracion_Tam);

module _deco2d() if (Decoracion != "ninguno") {
    x = (Decoracion_Lado=="izquierda") ? -Decoracion_Tam-3
      : (Decoracion_Lado=="arriba")    ? _w/2
      :                                  _w + Decoracion_Tam + 1;
    y = (Decoracion_Lado=="arriba") ? Font_Size + Decoracion_Tam*0.4 : _cy;
    translate([x + Deco_X, y + Deco_Y]) _forma2d();
}
module _content2d() { _name2d(); _deco2d(); }

// aros: pestaña redondeada + agujero
module _aro_tab(ringx, anchorx) hull() {
    translate([ringx,   _cy]) circle(Aro_R+2);
    translate([anchorx, _cy]) circle(Aro_R+2);   // ancla interna: garantiza que quede pegado
}
_lx = -3 + Ring_Offset;
_rx = _w + 3 + Aro_Ajuste_Der;

module _aros_tabs() {
    if (Aro_Lado=="izquierda" || Aro_Lado=="ambos") _aro_tab(_lx, Border_Size);
    if (Aro_Lado=="derecha"   || Aro_Lado=="ambos") _aro_tab(_rx, _w - Font_Size*0.2);
}
module _aros_holes() {
    if (Aro_Lado=="izquierda" || Aro_Lado=="ambos")
        translate([_lx, _cy, -1]) cylinder(h=Plate_Height+2, r=Aro_R);
    if (Aro_Lado=="derecha"   || Aro_Lado=="ambos")
        translate([_rx, _cy, -1]) cylinder(h=Plate_Height+2, r=Aro_R);
}

// ===============================
//   3D
// ===============================
module base_solida() linear_extrude(Plate_Height) {
    offset(r = Border_Size) _content2d();
    _aros_tabs();
}
module base_pieza() difference() { base_solida(); _aros_holes(); }

module texto_pieza() translate([0,0,Plate_Height])
    linear_extrude(Text_Height) _content2d();

// ===============================
//   RENDER
// ===============================
if (Export_Part=="base") {
    base_pieza();
} else if (Export_Part=="texto") {
    if (Multicolor_AMS)
        texto_pieza();                              // en su posición real, para alinear con la base
    else
        translate([0,0,-Plate_Height]) texto_pieza(); // apoyada en el suelo, para imprimir sola
} else {
    color(Base_Color) base_pieza();
    color(Text_Color) texto_pieza();
}
