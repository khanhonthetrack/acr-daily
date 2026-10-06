// The stages on Earth, for the pages' own drawings (home, stage statistics, run viewer) and the satellite links.
// The game's coordinates are a mirror image of the real place; for a stage lined up with the real roads (geofits.js)
// the pages draw it as it really is: earthScreen() turns game (x, z) into screen metres (east right, north up).
import { GEO_FITS } from './geofits.js';

/** track -> [lat, lon, rotDeg, scale] of the game's (0, 0), for the stages that line up (every map is mirrored in x). */
export const EARTH = Object.fromEntries(Object.entries(GEO_FITS).filter(([, f]) => f.ok)
  .map(([t, f]) => [t, [f.lat, f.lon, f.rotDeg, f.scale || 1]]));

/** The same, as browser code to put in a page's script. */
export const EARTH_JS = `var EARTH=${JSON.stringify(EARTH)};
function earthEN(g,p){var q=g[3],xm=-p[0]*q,zm=p[1]*q,r=g[2]*Math.PI/180,c=Math.cos(r),s=Math.sin(r);return [xm*c-zm*s,xm*s+zm*c]}
function earthLL(g,p){var en=earthEN(g,p);return [g[0]+en[1]/111132.954,g[1]+en[0]/(111319.49*Math.cos(g[0]*Math.PI/180))]}
function earthScreen(g){return g?function(p){var en=earthEN(g,p);return [en[0],-en[1]]}:function(p){return p}}
function earthAngle(pts,W,H,pad,north){
  var mx=0,mz=0,i,n=pts.length;for(i=0;i<n;i++){mx+=pts[i][0];mz+=pts[i][1]}mx/=n;mz/=n;
  var sxx=0,szz=0,sxz=0;for(i=0;i<n;i++){var dx=pts[i][0]-mx,dz=pts[i][1]-mz;sxx+=dx*dx;szz+=dz*dz;sxz+=dx*dz}
  var best=-0.5*Math.atan2(2*sxz,sxx-szz);if(!north)return best;
  function fill(a){var c=Math.cos(a),s=Math.sin(a),x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;
    for(var j=0;j<n;j++){var x=(pts[j][0]-mx)*c-(pts[j][1]-mz)*s,y=(pts[j][0]-mx)*s+(pts[j][1]-mz)*c;
      x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y)}
    return Math.min((W-2*pad)/(x1-x0||1),(H-2*pad)/(y1-y0||1))}
  return fill(0)>=0.75*fill(best)?0:best;   // north up, unless that leaves the drawing much smaller
}`;
