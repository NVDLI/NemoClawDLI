/*! js-yaml 5.2.2 https://github.com/nodeca/js-yaml @license MIT */
//#region src/tag.ts
var e = Symbol("NOT_RESOLVED"), t = Symbol("MERGE_KEY");
function n(e, t) {
	var n, r, i, a, o, s;
	return {
		tagName: e,
		nodeKind: "scalar",
		implicit: (n = t.implicit) == null ? !1 : n,
		matchByTagPrefix: (r = t.matchByTagPrefix) == null ? !1 : r,
		implicitFirstChars: (i = t.implicitFirstChars) == null ? null : i,
		resolve: t.resolve,
		identify: (a = t.identify) == null ? null : a,
		represent: (o = t.represent) == null ? ((e) => String(e)) : o,
		representTagName: (s = t.representTagName) == null ? null : s
	};
}
function r(e, t) {
	var n, r, i, a, o;
	let s = t.finalize === void 0;
	return {
		tagName: e,
		nodeKind: "sequence",
		implicit: !1,
		matchByTagPrefix: (n = t.matchByTagPrefix) == null ? !1 : n,
		create: t.create,
		addItem: t.addItem,
		finalize: (r = t.finalize) == null ? ((e) => e) : r,
		carrierIsResult: s,
		identify: (i = t.identify) == null ? null : i,
		represent: (a = t.represent) == null ? ((e) => e) : a,
		representTagName: (o = t.representTagName) == null ? null : o
	};
}
function i(e, t) {
	var n, r, i, a, o;
	let s = t.finalize === void 0;
	return {
		tagName: e,
		nodeKind: "mapping",
		implicit: !1,
		matchByTagPrefix: (n = t.matchByTagPrefix) == null ? !1 : n,
		create: t.create,
		addPair: t.addPair,
		has: t.has,
		keys: t.keys,
		get: t.get,
		finalize: (r = t.finalize) == null ? ((e) => e) : r,
		carrierIsResult: s,
		identify: (i = t.identify) == null ? null : i,
		represent: (a = t.represent) == null ? ((e) => e) : a,
		representTagName: (o = t.representTagName) == null ? null : o
	};
}
//#endregion
//#region src/tag/scalar/str.ts
var a = n("tag:yaml.org,2002:str", {
	resolve: (e) => e,
	identify: (e) => typeof e == "string"
}), o = [
	"",
	"~",
	"null",
	"Null",
	"NULL"
], s = n("tag:yaml.org,2002:null", {
	implicit: !0,
	implicitFirstChars: [
		"",
		"~",
		"n",
		"N"
	],
	resolve: (t) => o.indexOf(t) === -1 ? e : null,
	identify: (e) => e === null,
	represent: () => "null"
}), c = n("tag:yaml.org,2002:null", {
	implicit: !0,
	implicitFirstChars: ["n"],
	resolve: (t, n) => t === "null" || n && t === "" ? null : e,
	identify: (e) => e === null,
	represent: () => "null"
}), l = [
	"",
	"~",
	"null",
	"Null",
	"NULL"
], u = n("tag:yaml.org,2002:null", {
	implicit: !0,
	implicitFirstChars: [
		"",
		"~",
		"n",
		"N"
	],
	resolve: (t) => l.indexOf(t) === -1 ? e : null,
	identify: (e) => e === null,
	represent: () => "null"
}), d = [
	"true",
	"True",
	"TRUE"
], f = [
	"false",
	"False",
	"FALSE"
], p = n("tag:yaml.org,2002:bool", {
	implicit: !0,
	implicitFirstChars: [
		"t",
		"T",
		"f",
		"F"
	],
	resolve: (t) => d.indexOf(t) === -1 ? f.indexOf(t) === -1 ? e : !1 : !0,
	identify: (e) => Object.prototype.toString.call(e) === "[object Boolean]",
	represent: (e) => e ? "true" : "false"
}), m = ["true"], h = ["false"], ee = n("tag:yaml.org,2002:bool", {
	implicit: !0,
	implicitFirstChars: ["t", "f"],
	resolve: (t) => m.indexOf(t) === -1 ? h.indexOf(t) === -1 ? e : !1 : !0,
	identify: (e) => Object.prototype.toString.call(e) === "[object Boolean]",
	represent: (e) => e ? "true" : "false"
}), te = [
	"true",
	"True",
	"TRUE",
	"y",
	"Y",
	"yes",
	"Yes",
	"YES",
	"on",
	"On",
	"ON"
], ne = [
	"false",
	"False",
	"FALSE",
	"n",
	"N",
	"no",
	"No",
	"NO",
	"off",
	"Off",
	"OFF"
], re = n("tag:yaml.org,2002:bool", {
	implicit: !0,
	implicitFirstChars: [
		"y",
		"Y",
		"n",
		"N",
		"t",
		"T",
		"f",
		"F",
		"o",
		"O"
	],
	resolve: (t) => te.indexOf(t) === -1 ? ne.indexOf(t) === -1 ? e : !1 : !0,
	identify: (e) => Object.prototype.toString.call(e) === "[object Boolean]",
	represent: (e) => e ? "true" : "false"
}), ie = /* @__PURE__ */ RegExp("^(?:0o[0-7]+|0x[0-9a-fA-F]+|[-+]?[0-9]+)$"), ae = /* @__PURE__ */ RegExp("^(?:[-+]?0b[0-1]+|[-+]?0o[0-7]+|[-+]?0x[0-9a-fA-F]+|[-+]?[0-9]+)$");
function oe(e) {
	let t = e, n = 1;
	return (t[0] === "-" || t[0] === "+") && (t[0] === "-" && (n = -1), t = t.slice(1)), t.startsWith("0b") ? n * parseInt(t.slice(2), 2) : t.startsWith("0o") ? n * parseInt(t.slice(2), 8) : t.startsWith("0x") ? n * parseInt(t.slice(2), 16) : n * parseInt(t, 10);
}
function se(t, n) {
	if (n) {
		if (!ae.test(t)) return e;
	} else if (!ie.test(t)) return e;
	let r = oe(t);
	return Number.isFinite(r) ? r : e;
}
var ce = n("tag:yaml.org,2002:int", {
	implicit: !0,
	implicitFirstChars: [
		"-",
		"+",
		..."0123456789"
	],
	resolve: se,
	identify: (e) => Number.isInteger(e) && !Object.is(e, -0) && e.toString(10).indexOf("e") < 0,
	represent: (e) => e.toString(10)
}), le = /* @__PURE__ */ RegExp("^-?(?:0|[1-9][0-9]*)$"), ue = /* @__PURE__ */ RegExp("^(?:[-+]?0b[0-1]+|[-+]?0o[0-7]+|[-+]?0x[0-9a-fA-F]+|[-+]?[0-9]+)$");
function de(e) {
	let t = e, n = 1;
	return (t[0] === "-" || t[0] === "+") && (t[0] === "-" && (n = -1), t = t.slice(1)), t.startsWith("0b") ? n * parseInt(t.slice(2), 2) : t.startsWith("0o") ? n * parseInt(t.slice(2), 8) : t.startsWith("0x") ? n * parseInt(t.slice(2), 16) : n * parseInt(t, 10);
}
function fe(t, n) {
	if (n) {
		if (!ue.test(t)) return e;
	} else if (!le.test(t)) return e;
	let r = de(t);
	return Number.isFinite(r) ? r : e;
}
var pe = n("tag:yaml.org,2002:int", {
	implicit: !0,
	implicitFirstChars: ["-", ..."0123456789"],
	resolve: fe,
	identify: (e) => Number.isInteger(e) && !Object.is(e, -0) && e.toString(10).indexOf("e") < 0,
	represent: (e) => e.toString(10)
}), me = /* @__PURE__ */ RegExp("^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?0x[0-9a-fA-F_]+|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+|[-+]?(?:0|[1-9][0-9_]*))$");
function he(e) {
	let t = e.replace(/_/g, ""), n = 1;
	if ((t[0] === "-" || t[0] === "+") && (t[0] === "-" && (n = -1), t = t.slice(1)), t.startsWith("0b")) return n * parseInt(t.slice(2), 2);
	if (t.startsWith("0x")) return n * parseInt(t.slice(2), 16);
	if (t.includes(":")) {
		let e = 0;
		for (let n of t.split(":")) e = e * 60 + Number(n);
		return n * e;
	}
	return t !== "0" && t[0] === "0" ? n * parseInt(t, 8) : n * parseInt(t, 10);
}
function ge(t) {
	if (!me.test(t)) return e;
	let n = he(t);
	return Number.isFinite(n) ? n : e;
}
var _e = n("tag:yaml.org,2002:int", {
	implicit: !0,
	implicitFirstChars: [
		"-",
		"+",
		..."0123456789"
	],
	resolve: ge,
	identify: (e) => Number.isInteger(e) && !Object.is(e, -0) && e.toString(10).indexOf("e") < 0,
	represent: (e) => e.toString(10)
}), ve = /* @__PURE__ */ RegExp("^(?:[-+]?[0-9]+(?:\\.[0-9]*)?(?:[eE][-+]?[0-9]+)?|[-+]?\\.[0-9]+(?:[eE][-+]?[0-9]+)?|[-+]?\\.(?:inf|Inf|INF)|\\.(?:nan|NaN|NAN))$"), ye = /* @__PURE__ */ RegExp("^(?:[-+]?\\.(?:inf|Inf|INF)|\\.(?:nan|NaN|NAN))$");
function be(t) {
	if (!ve.test(t)) return e;
	let n = t.toLowerCase(), r = n[0] === "-" ? -1 : 1;
	if ("+-".includes(n[0]) && (n = n.slice(1)), n === ".inf") return r === 1 ? Infinity : -Infinity;
	if (n === ".nan") return NaN;
	let i = r * parseFloat(n);
	return Number.isFinite(i) || ye.test(t) ? i : e;
}
function xe(e) {
	if (isNaN(e)) return ".nan";
	if (e === Infinity) return ".inf";
	if (e === -Infinity) return "-.inf";
	if (Object.is(e, -0)) return "-0.0";
	let t = e.toString(10);
	return /^[-+]?[0-9]+e/.test(t) ? t.replace("e", ".e") : t;
}
var Se = n("tag:yaml.org,2002:float", {
	implicit: !0,
	implicitFirstChars: [
		"-",
		"+",
		".",
		..."0123456789"
	],
	resolve: be,
	identify: (e) => typeof e == "number" && (!Number.isInteger(e) || Object.is(e, -0) || e.toString(10).indexOf("e") >= 0),
	represent: xe
}), Ce = /* @__PURE__ */ RegExp("^-?(?:0|[1-9][0-9]*)(?:\\.[0-9]*)?(?:[eE][-+]?[0-9]+)?$"), we = /* @__PURE__ */ RegExp("^(?:[-+]?[0-9]+(?:\\.[0-9]*)?(?:[eE][-+]?[0-9]+)?|[-+]?\\.[0-9]+(?:[eE][-+]?[0-9]+)?|[-+]?\\.(?:inf|Inf|INF)|\\.(?:nan|NaN|NAN))$");
function Te(t, n) {
	if (n) {
		if (!we.test(t)) return e;
		let n = t.toLowerCase(), r = n[0] === "-" ? -1 : 1;
		if ("+-".includes(n[0]) && (n = n.slice(1)), n === ".inf") return r === 1 ? Infinity : -Infinity;
		if (n === ".nan") return NaN;
		let i = r * parseFloat(n);
		return Number.isFinite(i) ? i : e;
	}
	if (!Ce.test(t)) return e;
	let r = Number(t);
	return Number.isFinite(r) ? r : e;
}
function Ee(e) {
	if (isNaN(e)) return ".nan";
	if (e === Infinity) return ".inf";
	if (e === -Infinity) return "-.inf";
	if (Object.is(e, -0)) return "-0.0";
	let t = e.toString(10);
	return /^[-+]?[0-9]+e/.test(t) ? t.replace("e", ".e") : t;
}
var De = n("tag:yaml.org,2002:float", {
	implicit: !0,
	implicitFirstChars: ["-", ..."0123456789"],
	resolve: Te,
	identify: (e) => typeof e == "number" && (!Number.isInteger(e) || Object.is(e, -0) || e.toString(10).indexOf("e") >= 0),
	represent: Ee
}), Oe = /* @__PURE__ */ RegExp("^(?:[-+]?(?:(?:[0-9][0-9_]*)?\\.[0-9_]*)(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\\.[0-9_]*|[-+]?\\.(?:inf|Inf|INF)|\\.(?:nan|NaN|NAN))$"), ke = /* @__PURE__ */ RegExp("^(?:[-+]?\\.(?:inf|Inf|INF)|\\.(?:nan|NaN|NAN))$");
function Ae(t) {
	if (!Oe.test(t)) return e;
	let n = t.toLowerCase().replace(/_/g, ""), r = n[0] === "-" ? -1 : 1;
	if ("+-".includes(n[0]) && (n = n.slice(1)), n === ".inf") return r === 1 ? Infinity : -Infinity;
	if (n === ".nan") return NaN;
	let i = 0;
	if (n.includes(":")) {
		for (let e of n.split(":")) i = i * 60 + Number(e);
		i *= r;
	} else i = r * parseFloat(n);
	return Number.isFinite(i) || ke.test(t) ? i : e;
}
function je(e) {
	if (isNaN(e)) return ".nan";
	if (e === Infinity) return ".inf";
	if (e === -Infinity) return "-.inf";
	if (Object.is(e, -0)) return "-0.0";
	let t = e.toString(10);
	return /^[-+]?[0-9]+e/.test(t) ? t.replace("e", ".e") : t;
}
var Me = n("tag:yaml.org,2002:float", {
	implicit: !0,
	implicitFirstChars: [
		"-",
		"+",
		".",
		..."0123456789"
	],
	resolve: Ae,
	identify: (e) => typeof e == "number" && (!Number.isInteger(e) || Object.is(e, -0) || e.toString(10).indexOf("e") >= 0),
	represent: je
}), Ne = n("tag:yaml.org,2002:merge", {
	implicit: !0,
	implicitFirstChars: ["<"],
	resolve: (n, r) => n === "<<" || r && n === "" ? t : e
}), Pe = /^[A-Za-z0-9+/]*={0,2}$/;
function Fe(t) {
	let n = t.replace(/\s/g, "");
	if (n.length % 4 != 0 || !Pe.test(n)) return e;
	let r = atob(n), i = new Uint8Array(r.length);
	for (let e = 0; e < r.length; e++) i[e] = r.charCodeAt(e);
	return i;
}
function Ie(e) {
	let t = "";
	for (let n = 0; n < e.length; n++) t += String.fromCharCode(e[n]);
	return btoa(t);
}
var Le = n("tag:yaml.org,2002:binary", {
	resolve: Fe,
	identify: (e) => Object.prototype.toString.call(e) === "[object Uint8Array]",
	represent: Ie
}), Re = /* @__PURE__ */ RegExp("^([0-9][0-9][0-9][0-9])-([0-9][0-9])-([0-9][0-9])$"), ze = /* @__PURE__ */ RegExp("^([0-9][0-9][0-9][0-9])-([0-9][0-9]?)-([0-9][0-9]?)(?:[Tt]|[ \\t]+)([0-9][0-9]?):([0-9][0-9]):([0-9][0-9])(?:\\.([0-9]*))?(?:[ \\t]*(Z|([-+])([0-9][0-9]?)(?::([0-9][0-9]))?))?$");
function Be(t) {
	let n = Re.exec(t);
	if (n === null && (n = ze.exec(t)), n === null) return e;
	let r = +n[1], i = n[2] - 1, a = +n[3];
	if (!n[4]) {
		let t = new Date(Date.UTC(r, i, a));
		return t.getUTCFullYear() !== r || t.getUTCMonth() !== i || t.getUTCDate() !== a ? e : t;
	}
	let o = +n[4], s = +n[5], c = +n[6], l = 0;
	if (o > 23 || s > 59 || c > 59) return e;
	if (n[7]) {
		let e = n[7].slice(0, 3);
		for (; e.length < 3;) e += "0";
		l = +e;
	}
	let u = new Date(Date.UTC(r, i, a, o, s, c, l));
	if (u.getUTCFullYear() !== r || u.getUTCMonth() !== i || u.getUTCDate() !== a) return e;
	if (n[9]) {
		let t = +n[10], r = +(n[11] || 0);
		if (t > 23 || r > 59) return e;
		let i = (t * 60 + r) * 6e4;
		u.setTime(u.getTime() - (n[9] === "-" ? -i : i));
	}
	return u;
}
var Ve = n("tag:yaml.org,2002:timestamp", {
	implicit: !0,
	implicitFirstChars: [..."0123456789"],
	resolve: Be,
	identify: (e) => e instanceof Date,
	represent: (e) => e.toISOString()
}), He = r("tag:yaml.org,2002:seq", {
	create: () => [],
	addItem: (e, t) => {
		e.push(t);
	},
	identify: Array.isArray
});
//#endregion
//#region src/common/object.ts
function Ue(e) {
	if (typeof e != "object" || !e || Array.isArray(e)) return !1;
	let t = Object.getPrototypeOf(e);
	return t === null || t === Object.prototype;
}
function We(e, t) {
	let n = {};
	for (let r of t) e[r] !== void 0 && (n[r] = e[r]);
	return n;
}
//#endregion
//#region src/tag/sequence/omap.ts
var Ge = r("tag:yaml.org,2002:omap", {
	create: () => ({
		list: [],
		seen: /* @__PURE__ */ new Set()
	}),
	addItem: (e, t) => {
		let n;
		if (t instanceof Map) {
			if (t.size !== 1) return "cannot resolve an ordered map item";
			n = t.keys().next().value;
		} else if (Ue(t)) {
			let e = Object.keys(t);
			if (e.length !== 1) return "cannot resolve an ordered map item";
			n = e[0];
		} else return "cannot resolve an ordered map item";
		return e.seen.has(n) ? "duplicate key in ordered map" : (e.seen.add(n), e.list.push(t), "");
	},
	finalize: (e) => e.list
}), Ke = r("tag:yaml.org,2002:pairs", {
	create: () => [],
	addItem: (e, t) => {
		if (t instanceof Map) return t.size === 1 ? (e.push(t.entries().next().value), "") : "cannot resolve a pairs item";
		if (Object.prototype.toString.call(t) !== "[object Object]") return "cannot resolve a pairs item";
		let n = t, r = Object.keys(n);
		return r.length === 1 ? (e.push([r[0], n[r[0]]]), "") : "cannot resolve a pairs item";
	}
}), qe = i("tag:yaml.org,2002:map", {
	create: () => ({}),
	identify: Ue,
	represent: (e) => {
		let t = /* @__PURE__ */ new Map();
		for (let n of Object.keys(e)) t.set(n, e[n]);
		return t;
	},
	addPair: (e, t, n) => {
		if (typeof t == "object" && t) return "object-based map does not support complex keys";
		let r = String(t);
		return r === "__proto__" ? Object.defineProperty(e, r, {
			value: n,
			enumerable: !0,
			configurable: !0,
			writable: !0
		}) : e[r] = n, "";
	},
	has: (e, t) => typeof t == "object" && t ? !1 : Object.prototype.hasOwnProperty.call(e, String(t)),
	keys: (e) => Object.keys(e),
	get: (e, t) => e[String(t)]
}), Je = i("tag:yaml.org,2002:set", {
	create: () => /* @__PURE__ */ new Set(),
	identify: (e) => e instanceof Set,
	represent: (e) => {
		let t = /* @__PURE__ */ new Map();
		for (let n of e) t.set(n, null);
		return t;
	},
	addPair: (e, t, n) => n === null ? (e.add(t), "") : "cannot resolve a set item",
	has: (e, t) => e.has(t),
	keys: (e) => e.keys(),
	get: () => null
});
//#endregion
//#region \0@oxc-project+runtime@0.137.0/helpers/esm/typeof.js
function g(e) {
	"@babel/helpers - typeof";
	return g = typeof Symbol == "function" && typeof Symbol.iterator == "symbol" ? function(e) {
		return typeof e;
	} : function(e) {
		return e && typeof Symbol == "function" && e.constructor === Symbol && e !== Symbol.prototype ? "symbol" : typeof e;
	}, g(e);
}
//#endregion
//#region \0@oxc-project+runtime@0.137.0/helpers/esm/toPrimitive.js
function Ye(e, t) {
	if (g(e) != "object" || !e) return e;
	var n = e[Symbol.toPrimitive];
	if (n !== void 0) {
		var r = n.call(e, t || "default");
		if (g(r) != "object") return r;
		throw TypeError("@@toPrimitive must return a primitive value.");
	}
	return (t === "string" ? String : Number)(e);
}
//#endregion
//#region \0@oxc-project+runtime@0.137.0/helpers/esm/toPropertyKey.js
function Xe(e) {
	var t = Ye(e, "string");
	return g(t) == "symbol" ? t : t + "";
}
//#endregion
//#region \0@oxc-project+runtime@0.137.0/helpers/esm/defineProperty.js
function _(e, t, n) {
	return (t = Xe(t)) in e ? Object.defineProperty(e, t, {
		value: n,
		enumerable: !0,
		configurable: !0,
		writable: !0
	}) : e[t] = n, e;
}
//#endregion
//#region src/schema.ts
function Ze() {
	return {
		scalar: {},
		sequence: {},
		mapping: {}
	};
}
function Qe() {
	return {
		scalar: [],
		sequence: [],
		mapping: []
	};
}
function $e(e) {
	let t = [];
	for (let n of e) {
		let e = t.length;
		for (let r = 0; r < t.length; r++) {
			let i = t[r];
			if (i.nodeKind === n.nodeKind && i.tagName === n.tagName && i.matchByTagPrefix === n.matchByTagPrefix) {
				e = r;
				break;
			}
		}
		t[e] = n;
	}
	return t;
}
var v = class e {
	constructor(e) {
		_(this, "tags", void 0), _(this, "implicitScalarTags", void 0), _(this, "implicitScalarByFirstChar", void 0), _(this, "implicitScalarAnyFirstChar", void 0), _(this, "defaultScalarTag", void 0), _(this, "defaultSequenceTag", void 0), _(this, "defaultMappingTag", void 0), _(this, "exact", void 0), _(this, "prefix", void 0);
		let t = $e(e), n = [], r = Ze(), i = Qe();
		for (let e of t) {
			if (e.nodeKind === "scalar" && e.implicit) {
				if (e.matchByTagPrefix) throw Error("Implicit scalar tags cannot match by tag prefix");
				n.push(e);
			}
			switch (e.nodeKind) {
				case "scalar":
					e.matchByTagPrefix ? i.scalar.push(e) : r.scalar[e.tagName] = e;
					break;
				case "sequence":
					e.matchByTagPrefix ? i.sequence.push(e) : r.sequence[e.tagName] = e;
					break;
				case "mapping":
					e.matchByTagPrefix ? i.mapping.push(e) : r.mapping[e.tagName] = e;
					break;
			}
		}
		let a = n.filter((e) => e.implicitFirstChars === null), o = /* @__PURE__ */ new Set();
		for (let e of n) if (e.implicitFirstChars !== null) for (let t of e.implicitFirstChars) o.add(t);
		let s = /* @__PURE__ */ new Map();
		for (let e of o) s.set(e, n.filter((t) => t.implicitFirstChars === null || t.implicitFirstChars.indexOf(e) !== -1));
		let c = r.scalar["tag:yaml.org,2002:str"];
		if (!c) throw Error("schema does not define the default scalar tag (tag:yaml.org,2002:str)");
		this.tags = t, this.implicitScalarTags = n, this.implicitScalarByFirstChar = s, this.implicitScalarAnyFirstChar = a, this.defaultScalarTag = c, this.defaultSequenceTag = r.sequence["tag:yaml.org,2002:seq"], this.defaultMappingTag = r.mapping["tag:yaml.org,2002:map"], this.exact = r, this.prefix = i;
	}
	withTags(...t) {
		let n = [];
		for (let e of t) n = n.concat(e);
		return new e([...this.tags, ...n]);
	}
}, et = new v([
	a,
	He,
	qe
]), tt = new v([
	...et.tags,
	c,
	ee,
	pe,
	De
]), nt = new v([
	...et.tags,
	s,
	p,
	ce,
	Se
]), rt = new v([
	...et.tags,
	u,
	re,
	_e,
	Me,
	Ve,
	Ne,
	Le,
	Ge,
	Ke,
	Je
]), it = i("tag:yaml.org,2002:map", {
	create: () => /* @__PURE__ */ new Map(),
	addPair: (e, t, n) => (e.set(t, n), ""),
	has: (e, t) => e.has(t),
	keys: (e) => e.keys(),
	get: (e, t) => e.get(t),
	identify: (e) => e instanceof Map || Ue(e),
	represent: (e) => {
		if (e instanceof Map) return e;
		let t = /* @__PURE__ */ new Map(), n = e;
		for (let e of Object.keys(n)) t.set(e, n[e]);
		return t;
	}
});
//#endregion
//#region src/tag/mapping/legacy_map.ts
function at(e) {
	if (Array.isArray(e)) {
		let t = Array.prototype.slice.call(e);
		for (let e = 0; e < t.length; e++) {
			if (Array.isArray(t[e])) return null;
			typeof t[e] == "object" && Object.prototype.toString.call(t[e]) === "[object Object]" && (t[e] = "[object Object]");
		}
		return String(t);
	}
	return typeof e == "object" && Object.prototype.toString.call(e) === "[object Object]" ? "[object Object]" : String(e);
}
var ot = i("tag:yaml.org,2002:map", {
	create: () => ({}),
	identify: Ue,
	represent: (e) => {
		let t = /* @__PURE__ */ new Map();
		for (let n of Object.keys(e)) t.set(n, e[n]);
		return t;
	},
	addPair: (e, t, n) => {
		let r = at(t);
		return r === null ? "nested arrays are not supported inside keys" : (r === "__proto__" ? Object.defineProperty(e, r, {
			value: n,
			enumerable: !0,
			configurable: !0,
			writable: !0
		}) : e[r] = n, "");
	},
	has: (e, t) => {
		let n = at(t);
		return n !== null && Object.prototype.hasOwnProperty.call(e, n);
	},
	keys: (e) => Object.keys(e),
	get: (e, t) => e[String(t)]
});
//#endregion
//#region \0@oxc-project+runtime@0.137.0/helpers/esm/objectSpread2.js
function st(e, t) {
	var n = Object.keys(e);
	if (Object.getOwnPropertySymbols) {
		var r = Object.getOwnPropertySymbols(e);
		t && (r = r.filter(function(t) {
			return Object.getOwnPropertyDescriptor(e, t).enumerable;
		})), n.push.apply(n, r);
	}
	return n;
}
function y(e) {
	for (var t = 1; t < arguments.length; t++) {
		var n = arguments[t] == null ? {} : arguments[t];
		t % 2 ? st(Object(n), !0).forEach(function(t) {
			_(e, t, n[t]);
		}) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(n)) : st(Object(n)).forEach(function(t) {
			Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(n, t));
		});
	}
	return e;
}
//#endregion
//#region src/common/snippet.ts
var ct = {
	maxLength: 79,
	indent: 1,
	linesBefore: 3,
	linesAfter: 2
};
function lt(e, t, n, r, i) {
	let a = "", o = "", s = Math.floor(i / 2) - 1;
	return r - t > s && (a = " ... ", t = r - s + a.length), n - r > s && (o = " ...", n = r + s - o.length), {
		str: a + e.slice(t, n).replace(/\t/g, "→") + o,
		pos: r - t + a.length
	};
}
function ut(e, t) {
	return " ".repeat(Math.max(t - e.length, 0)) + e;
}
function dt(e, t) {
	if (!e.buffer) return null;
	let n = y(y({}, ct), t), r = /\r?\n|\r|\0/g, i = [0], a = [], o, s = -1;
	for (; o = r.exec(e.buffer);) a.push(o.index), i.push(o.index + o[0].length), e.position <= o.index && s < 0 && (s = i.length - 2);
	s < 0 && (s = i.length - 1);
	let c = "", l = Math.min(e.line + n.linesAfter, a.length).toString().length, u = n.maxLength - (n.indent + l + 3);
	for (let t = 1; t <= n.linesBefore && !(s - t < 0); t++) {
		let r = lt(e.buffer, i[s - t], a[s - t], e.position - (i[s] - i[s - t]), u);
		c = `${" ".repeat(n.indent)}${ut((e.line - t + 1).toString(), l)} | ${r.str}\n${c}`;
	}
	let d = lt(e.buffer, i[s], a[s], e.position, u);
	c += `${" ".repeat(n.indent)}${ut((e.line + 1).toString(), l)} | ${d.str}\n`, c += `${"-".repeat(n.indent + l + 3 + d.pos)}^\n`;
	for (let t = 1; t <= n.linesAfter && !(s + t >= a.length); t++) {
		let r = lt(e.buffer, i[s + t], a[s + t], e.position - (i[s] - i[s + t]), u);
		c += `${" ".repeat(n.indent)}${ut((e.line + t + 1).toString(), l)} | ${r.str}\n`;
	}
	return c.replace(/\n$/, "");
}
//#endregion
//#region src/common/exception.ts
function ft(e, t) {
	let n = "";
	return e.mark ? (e.mark.name && (n += `in "${e.mark.name}" `), n += `(${e.mark.line + 1}:${e.mark.column + 1})`, !t && e.mark.snippet && (n += `\n\n${e.mark.snippet}`), `${e.reason} ${n}`) : e.reason;
}
var b = class extends Error {
	constructor(e, t) {
		super(), _(this, "reason", void 0), _(this, "mark", void 0), this.name = "YAMLException", this.reason = e, this.mark = t, this.message = ft(this, !1), Error.captureStackTrace && Error.captureStackTrace(this, this.constructor);
	}
	toString(e) {
		return `${this.name}: ${ft(this, e)}`;
	}
};
function pt(e, t, n, r = "") {
	let i = 0, a = 0;
	for (let n = 0; n < t; n++) {
		let t = e.charCodeAt(n);
		t === 10 ? (i++, a = n + 1) : t === 13 && (i++, e.charCodeAt(n + 1) === 10 && n++, a = n + 1);
	}
	let o = {
		name: r,
		buffer: e,
		position: t,
		line: i,
		column: t - a
	};
	throw o.snippet = dt(o), new b(n, o);
}
//#endregion
//#region src/parser/events.ts
var mt = 1, ht = 2, gt = 3, _t = 4, vt = 5, yt = 6, bt = 1, xt = 2, St = 3, Ct = 4, wt = 5, Tt = 1, Et = 2, Dt = 1, Ot = 2, kt = 3, At = -1;
function jt(e) {
	switch (e) {
		case 48: return "\0";
		case 97: return "\x07";
		case 98: return "\b";
		case 116: return "	";
		case 9: return "	";
		case 110: return "\n";
		case 118: return "\v";
		case 102: return "\f";
		case 114: return "\r";
		case 101: return "\x1B";
		case 32: return " ";
		case 34: return "\"";
		case 47: return "/";
		case 92: return "\\";
		case 78: return "";
		case 95: return "\xA0";
		case 76: return "\u2028";
		case 80: return "\u2029";
		default: return "";
	}
}
var Mt = Array(256), Nt = Array(256);
for (let e = 0; e < 256; e++) Mt[e] = +!!jt(e), Nt[e] = jt(e);
function Pt(e) {
	return e <= 65535 ? String.fromCharCode(e) : String.fromCharCode((e - 65536 >> 10) + 55296, (e - 65536 & 1023) + 56320);
}
function Ft(e) {
	return e >= 48 && e <= 57 ? e - 48 : (e | 32) - 97 + 10;
}
function It(e) {
	return e === 120 ? 2 : e === 117 ? 4 : 8;
}
function Lt(e, t, n) {
	let r = 0;
	for (; t < n;) {
		let n = e.charCodeAt(t);
		if (n === 10) r++, t++;
		else if (n === 13) r++, t++, e.charCodeAt(t) === 10 && t++;
		else if (n === 32 || n === 9) t++;
		else break;
	}
	return {
		position: t,
		breaks: r
	};
}
function Rt(e) {
	return e === 1 ? " " : "\n".repeat(e - 1);
}
function zt(e, t, n) {
	let r = "", i = t, a = t, o = t;
	for (; i < n;) {
		let t = e.charCodeAt(i);
		if (t === 10 || t === 13) {
			r += e.slice(a, o);
			let t = Lt(e, i, n);
			r += Rt(t.breaks), i = a = o = t.position;
		} else i++, t !== 32 && t !== 9 && (o = i);
	}
	return r + e.slice(a, o);
}
function Bt(e, t, n) {
	let r = "", i = t, a = t, o = t;
	for (; i < n;) {
		let t = e.charCodeAt(i);
		if (t === 39) r += e.slice(a, i) + "'", i += 2, a = o = i;
		else if (t === 10 || t === 13) {
			r += e.slice(a, o);
			let t = Lt(e, i, n);
			r += Rt(t.breaks), i = a = o = t.position;
		} else i++, t !== 32 && t !== 9 && (o = i);
	}
	return r + e.slice(a, n);
}
function Vt(e, t, n) {
	let r = "", i = t, a = t, o = t;
	for (; i < n;) {
		let t = e.charCodeAt(i);
		if (t === 92) {
			r += e.slice(a, i), i++;
			let t = e.charCodeAt(i);
			if (t === 10 || t === 13) i = Lt(e, i, n).position;
			else if (t < 256 && Mt[t]) r += Nt[t], i++;
			else {
				let n = It(t), a = 0;
				for (; n > 0; n--) {
					i++;
					let t = Ft(e.charCodeAt(i));
					a = (a << 4) + t;
				}
				r += Pt(a), i++;
			}
			a = o = i;
		} else if (t === 10 || t === 13) {
			r += e.slice(a, o);
			let t = Lt(e, i, n);
			r += Rt(t.breaks), i = a = o = t.position;
		} else i++, t !== 32 && t !== 9 && (o = i);
	}
	return r + e.slice(a, n);
}
function Ht(e, t, n, r, i, a) {
	let o = r < 0 ? 0 : r, s = e.slice(t, n).replace(/\r\n?/g, "\n"), c = s === "" ? [] : (s.endsWith("\n") ? s.slice(0, -1) : s).split("\n"), l = "", u = !1, d = 0, f = !1;
	for (let e of c) {
		let t = 0;
		for (; t < o && e.charCodeAt(t) === 32;) t++;
		if (r < 0 || t >= e.length) {
			d++;
			continue;
		}
		let n = e.slice(o), i = n.charCodeAt(0);
		a ? i === 32 || i === 9 ? (f = !0, l += "\n".repeat(u ? 1 + d : d)) : f ? (f = !1, l += "\n".repeat(d + 1)) : d === 0 ? u && (l += " ") : l += "\n".repeat(d) : l += "\n".repeat(u ? 1 + d : d), l += n, u = !0, d = 0;
	}
	return i === 3 ? l += "\n".repeat(u ? 1 + d : d) : i !== 2 && u && (l += "\n"), l;
}
function Ut(e, t) {
	if (t.valueStart === At) return "";
	let { valueStart: n, valueEnd: r } = t;
	if (t.fast) return e.slice(n, r);
	switch (t.style) {
		case 2: return Bt(e, n, r);
		case 3: return Vt(e, n, r);
		case 4: return Ht(e, n, r, t.indent, t.chomping, !1);
		case 5: return Ht(e, n, r, t.indent, t.chomping, !0);
		default: return zt(e, n, r);
	}
}
//#endregion
//#region src/common/tagname.ts
var Wt = {
	"!": "!",
	"!!": "tag:yaml.org,2002:"
};
function Gt(e) {
	return encodeURI(e).replace(/!/g, "%21");
}
function Kt(e, t) {
	var n, r;
	if (e.startsWith("!<") && e.endsWith(">")) return decodeURIComponent(e.slice(2, -1));
	let i = e.indexOf("!", 1), a = i === -1 ? "!" : e.slice(0, i + 1), o = (n = (r = t == null ? void 0 : t[a]) == null ? Wt[a] : r) == null ? a : n;
	return decodeURIComponent(o) + decodeURIComponent(e.slice(a.length));
}
function qt(e) {
	let t = e;
	return t.charCodeAt(0) === 33 ? (t = t.slice(1), `!${Gt(t)}`) : t.slice(0, 18) === "tag:yaml.org,2002:" ? `!!${Gt(t.slice(18))}` : `!<${Gt(t)}>`;
}
//#endregion
//#region src/parser/constructor.ts
var x = -1, Jt = {
	filename: "",
	schema: nt,
	json: !1,
	maxTotalMergeKeys: 1e4,
	maxAliases: -1
};
function Yt(e) {
	return "tagStart" in e && e.tagStart !== x ? e.tagStart : "anchorStart" in e && e.anchorStart !== x ? e.anchorStart : "valueStart" in e && e.valueStart !== x ? e.valueStart : "start" in e ? e.start : 0;
}
function S(e, t) {
	pt(e.source, e.position, t, e.filename);
}
function Xt(e, t, n, r) {
	try {
		return n.finalize(r);
	} catch (n) {
		if (n instanceof b) throw n;
		pt(e.source, t, n instanceof Error ? n.message : String(n), e.filename);
	}
}
function Zt(e, t, n) {
	let r = e[n];
	if (r) return r;
	for (let e of t) if (n.startsWith(e.tagName)) return e;
}
function Qt(e, t, n, r, i) {
	let a = Zt(t, n, r);
	if (a) return a;
	S(e, `unknown ${i} tag !<${r}>`);
}
function $t(t, n) {
	let r = Ut(t.source, n), i = n.tagStart === x ? "" : t.source.slice(n.tagStart, n.tagEnd), a = t.schema.defaultScalarTag;
	if (i !== "") {
		var o;
		if (i === "!") return {
			value: r,
			tag: a
		};
		let n = Kt(i, t.tagHandlers), s = Zt(t.schema.exact.scalar, t.schema.prefix.scalar, n);
		if (s) {
			let i = s.resolve(r, !0, n);
			return i === e && S(t, `cannot resolve a node with !<${n}> explicit tag`), {
				value: i,
				tag: s
			};
		}
		let c = (o = Zt(t.schema.exact.mapping, t.schema.prefix.mapping, n)) == null ? Zt(t.schema.exact.sequence, t.schema.prefix.sequence, n) : o;
		if (c) {
			r !== "" && S(t, `cannot resolve a node with !<${n}> explicit tag`);
			let e = c.create(n);
			return {
				value: c.carrierIsResult ? e : Xt(t, t.position, c, e),
				tag: c
			};
		}
		S(t, `unknown scalar tag !<${n}>`);
	}
	if (n.style === 1) {
		var s;
		let n = (s = t.schema.implicitScalarByFirstChar.get(r.charAt(0))) == null ? t.schema.implicitScalarAnyFirstChar : s;
		for (let t of n) {
			let n = t.resolve(r, !1, t.tagName);
			if (n !== e) return {
				value: n,
				tag: t
			};
		}
	}
	return {
		value: a.resolve(r, !1, a.tagName),
		tag: a
	};
}
function en(e, t, n, r, i, a) {
	let o = t.tagStart === x ? "" : e.source.slice(t.tagStart, t.tagEnd), s = o === "" || o === "!" ? i : Kt(o, e.tagHandlers);
	return {
		tagName: s,
		tag: Qt(e, n, r, s, a)
	};
}
function tn(e) {
	return e.nodeKind === "mapping";
}
function nn(e, t, n, r) {
	for (let a of r.keys(n)) {
		var i;
		if (e.maxTotalMergeKeys !== -1 && ++e.totalMergeKeys > e.maxTotalMergeKeys && S(e, `merge keys exceeded maxTotalMergeKeys (${e.maxTotalMergeKeys})`), t.tag.has(t.value, a)) continue;
		let o = t.tag.addPair(t.value, a, r.get(n, a));
		o && S(e, o), ((i = t.overridable) == null ? t.overridable = /* @__PURE__ */ new Set() : i).add(a);
	}
}
function rn(e, t, n, r) {
	if (e.position = t.keyPosition, tn(r)) nn(e, t, n, r);
	else if (r.nodeKind === "sequence" && Array.isArray(n)) for (let r of n) nn(e, t, r, t.tag);
	else S(e, "cannot merge mappings; the provided source object is unacceptable");
}
function an(e, n, r, i, a) {
	var o, s;
	if (e.position = n.keyPosition, r === t) {
		rn(e, n, i, a);
		return;
	}
	!e.json && n.tag.has(n.value, r) && !((o = n.overridable) != null && o.has(r)) && S(e, "duplicated mapping key");
	let c = n.tag.addPair(n.value, r, i);
	c && S(e, c), (s = n.overridable) == null || s.delete(r);
}
function on(e, t, n) {
	let r = e.frames[e.frames.length - 1];
	if (r.kind === "document") r.value = t, r.hasValue = !0;
	else if (r.kind === "sequence") {
		r.merge && (tn(n) || S(e, "cannot merge mappings; the provided source object is unacceptable"));
		let i = r.tag.addItem(r.value, t, r.index++);
		i && S(e, i);
	} else if (r.hasKey) {
		let i = r.key;
		r.key = void 0, r.hasKey = !1, an(e, r, i, t, n);
	} else r.key = t, r.keyPosition = e.position, r.hasKey = !0;
}
function sn(e, t, n, r, i) {
	if (t.anchorStart !== x) {
		let a = {
			value: n,
			tag: r,
			isValueFinal: i
		};
		return e.anchors.set(e.source.slice(t.anchorStart, t.anchorEnd), a), a;
	}
	return null;
}
function cn(e, n) {
	let r = y(y(y({}, Jt), n), {}, {
		events: e,
		documents: [],
		eventIndex: 0,
		position: 0,
		frames: [],
		anchors: /* @__PURE__ */ new Map(),
		tagHandlers: Object.create(null),
		totalMergeKeys: 0,
		aliasCount: 0
	});
	for (; r.eventIndex < r.events.length;) {
		let e = r.events[r.eventIndex++];
		switch (r.position = Yt(e), e.type) {
			case 1:
				r.anchors = /* @__PURE__ */ new Map(), r.aliasCount = 0, r.tagHandlers = Object.create(null);
				for (let t of e.directives) t.kind === "tag" && (r.tagHandlers[t.handle] = t.prefix);
				r.frames.push({
					kind: "document",
					position: r.position,
					value: void 0,
					hasValue: !1
				});
				break;
			case 4: {
				let { value: t, tag: n } = $t(r, e);
				sn(r, e, t, n, !0), on(r, t, n);
				break;
			}
			case 2: {
				let n = en(r, e, r.schema.exact.sequence, r.schema.prefix.sequence, "tag:yaml.org,2002:seq", "sequence"), i = n.tag.create(n.tagName), a = sn(r, e, i, n.tag, n.tag.carrierIsResult), o = r.frames[r.frames.length - 1], s = o !== void 0 && o.kind === "mapping" && o.hasKey && o.key === t;
				r.frames.push({
					kind: "sequence",
					position: r.position,
					value: i,
					tag: n.tag,
					anchor: a,
					index: 0,
					merge: s
				});
				break;
			}
			case 3: {
				let t = en(r, e, r.schema.exact.mapping, r.schema.prefix.mapping, "tag:yaml.org,2002:map", "mapping"), n = t.tag.create(t.tagName), i = sn(r, e, n, t.tag, t.tag.carrierIsResult);
				r.frames.push({
					kind: "mapping",
					position: r.position,
					value: n,
					tag: t.tag,
					anchor: i,
					key: void 0,
					keyPosition: r.position,
					hasKey: !1,
					overridable: null
				});
				break;
			}
			case 5: {
				r.maxAliases !== -1 && ++r.aliasCount > r.maxAliases && S(r, `aliases exceeded maxAliases (${r.maxAliases})`);
				let t = r.source.slice(e.anchorStart, e.anchorEnd), n = r.anchors.get(t);
				n || S(r, `unidentified alias "${t}"`), n.isValueFinal || S(r, `recursive alias "${t}" is not supported for tag ${n.tag.tagName} because it uses finalize()`), on(r, n.value, n.tag);
				break;
			}
			case 6: {
				let e = r.frames.pop();
				if (e.kind === "document") r.documents.push(e.value);
				else {
					let t = e.tag.carrierIsResult ? e.value : Xt(r, e.position, e.tag, e.value);
					e.anchor && (e.anchor.value = t, e.anchor.isValueFinal = !0), on(r, t, e.tag);
				}
				break;
			}
		}
	}
	return r.documents;
}
//#endregion
//#region src/parser/parser.ts
var C = -1, ln = Object.prototype.hasOwnProperty, w = 1, un = 2, dn = 3, fn = 4, pn = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x84\x86-\x9F\uFFFE\uFFFF]|[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?:[^\uD800-\uDBFF]|^)[\uDC00-\uDFFF]/, mn = /[,\[\]{}]/, hn = /^(?:!|!!|![0-9A-Za-z-]+!)$/, gn = String.raw`(?:%[0-9A-Fa-f]{2}|[0-9A-Za-z\-#;/?:@&=+$,_.!~*'()\[\]])`, _n = String.raw`(?:%[0-9A-Fa-f]{2}|[0-9A-Za-z\-#;/?:@&=+$.~*'()_])`, vn = RegExp(`^(?:${gn})*$`), yn = RegExp(`^(?:${_n})+$`), bn = RegExp(`^(?:!(?:${gn})*|${_n}(?:${gn})*)$`), xn = {
	filename: "",
	maxDepth: 100
};
function Sn(e, t, n) {
	e.events.push({
		type: 1,
		explicitStart: t,
		explicitEnd: n,
		directives: e.directives
	});
}
function Cn(e, t, n, r, i, a, o) {
	e.events.push({
		type: 2,
		start: t,
		anchorStart: n,
		anchorEnd: r,
		tagStart: i,
		tagEnd: a,
		style: o
	});
}
function wn(e, t, n, r, i, a, o) {
	e.events.push({
		type: 3,
		start: t,
		anchorStart: n,
		anchorEnd: r,
		tagStart: i,
		tagEnd: a,
		style: o
	});
}
function Tn(e, t) {
	e.events.splice(t.eventsLength, 0, {
		type: 3,
		start: t.position,
		anchorStart: C,
		anchorEnd: C,
		tagStart: C,
		tagEnd: C,
		style: 2
	});
}
function T(e, t, n, r, i, a, o, s, c = 1, l = -1, u = !1) {
	e.events.push({
		type: 4,
		valueStart: t,
		valueEnd: n,
		anchorStart: r,
		anchorEnd: i,
		tagStart: a,
		tagEnd: o,
		style: s,
		chomping: c,
		indent: l,
		fast: u
	});
}
function En(e, t, n) {
	e.events.push({
		type: 5,
		anchorStart: t,
		anchorEnd: n
	});
}
function E(e) {
	e.events.push({ type: 6 });
}
function D(e) {
	T(e, C, C, C, C, C, C, 1);
}
function Dn() {
	return {
		anchorStart: C,
		anchorEnd: C,
		tagStart: C,
		tagEnd: C
	};
}
function O(e) {
	return {
		position: e.position,
		line: e.line,
		lineStart: e.lineStart,
		lineIndent: e.lineIndent,
		firstTabInLine: e.firstTabInLine,
		eventsLength: e.events.length
	};
}
function k(e, t) {
	e.position = t.position, e.line = t.line, e.lineStart = t.lineStart, e.lineIndent = t.lineIndent, e.firstTabInLine = t.firstTabInLine, e.events.length = t.eventsLength;
}
function A(e, t) {
	pt(e.input.slice(0, e.length), e.position, t, e.filename);
}
function j(e) {
	return e === 10 || e === 13;
}
function M(e) {
	return e === 9 || e === 32;
}
function N(e) {
	return M(e) || j(e);
}
function P(e) {
	return e === 0 || N(e);
}
function F(e) {
	return e === 44 || e === 91 || e === 93 || e === 123 || e === 125;
}
function On(e) {
	return e >= 48 && e <= 57 ? e - 48 : -1;
}
function kn(e) {
	if (e >= 48 && e <= 57) return e - 48;
	let t = e | 32;
	return t >= 97 && t <= 102 ? t - 97 + 10 : -1;
}
function An(e) {
	return e === 120 ? 2 : e === 117 ? 4 : e === 85 ? 8 : 0;
}
function jn(e) {
	return e === 48 || e === 97 || e === 98 || e === 116 || e === 9 || e === 110 || e === 118 || e === 102 || e === 114 || e === 101 || e === 32 || e === 34 || e === 47 || e === 92 || e === 78 || e === 95 || e === 76 || e === 80;
}
function Mn(e) {
	e.input.charCodeAt(e.position) === 10 ? e.position++ : (e.position++, e.input.charCodeAt(e.position) === 10 && e.position++), e.line++, e.lineStart = e.position, e.lineIndent = 0, e.firstTabInLine = -1;
}
function I(e, t) {
	let n = 0, r = e.input.charCodeAt(e.position), i = e.position === e.lineStart || N(e.input.charCodeAt(e.position - 1));
	for (; r !== 0;) {
		for (; M(r);) i = !0, r === 9 && e.firstTabInLine === -1 && (e.firstTabInLine = e.position), r = e.input.charCodeAt(++e.position);
		if (t && i && r === 35) do
			r = e.input.charCodeAt(++e.position);
		while (!j(r) && r !== 0);
		if (!j(r)) break;
		for (Mn(e), n++, i = !0, r = e.input.charCodeAt(e.position); r === 32;) e.lineIndent++, r = e.input.charCodeAt(++e.position);
	}
	return n;
}
function L(e, t = e.position) {
	let n = e.input.charCodeAt(t);
	if ((n === 45 || n === 46) && n === e.input.charCodeAt(t + 1) && n === e.input.charCodeAt(t + 2)) {
		let n = e.input.charCodeAt(t + 3);
		return n === 0 || N(n);
	}
	return !1;
}
function Nn(e) {
	let t = e.input.charCodeAt(e.position);
	for (; t !== 0 && !j(t);) t = e.input.charCodeAt(++e.position);
}
function Pn(e, t, n) {
	pn.test(e.input.slice(t, n)) && A(e, "the stream contains non-printable characters");
}
function Fn(e, t, n) {
	if (e.input.charCodeAt(e.position) !== 33) return !1;
	t.tagStart !== C && A(e, "duplication of a tag property");
	let r = e.position, i = !1, a = !1, o = "!", s = e.input.charCodeAt(++e.position);
	s === 60 ? (i = !0, s = e.input.charCodeAt(++e.position)) : s === 33 && (a = !0, o = "!!", s = e.input.charCodeAt(++e.position));
	let c = e.position, l;
	if (i) {
		for (; s !== 0 && s !== 62;) s = e.input.charCodeAt(++e.position);
		s !== 62 && A(e, "unexpected end of the stream within a verbatim tag"), l = e.input.slice(c, e.position), e.position++;
	} else {
		for (; s !== 0 && !N(s) && !(n && F(s));) s === 33 && (a ? A(e, "tag suffix cannot contain exclamation marks") : (o = e.input.slice(c - 1, e.position + 1), hn.test(o) || A(e, "named tag handle cannot contain such characters"), a = !0, c = e.position + 1)), s = e.input.charCodeAt(++e.position);
		l = e.input.slice(c, e.position), mn.test(l) && A(e, "tag suffix cannot contain flow indicator characters");
	}
	return l && !(i ? vn.test(l) : yn.test(l)) && A(e, `tag name cannot contain such characters: ${l}`), !i && o !== "!" && o !== "!!" && !ln.call(e.tagHandlers, o) && A(e, `undeclared tag handle "${o}"`), t.tagStart = r, t.tagEnd = e.position, !0;
}
function In(e, t) {
	if (e.input.charCodeAt(e.position) !== 38) return !1;
	t.anchorStart !== C && A(e, "duplication of an anchor property"), e.position++;
	let n = e.position;
	for (; e.input.charCodeAt(e.position) !== 0 && !N(e.input.charCodeAt(e.position)) && !F(e.input.charCodeAt(e.position));) e.position++;
	return e.position === n && A(e, "name of an anchor node must contain at least one character"), t.anchorStart = n, t.anchorEnd = e.position, !0;
}
function Ln(e, t) {
	if (e.input.charCodeAt(e.position) !== 42) return !1;
	(t.anchorStart !== C || t.tagStart !== C) && A(e, "alias node should not have any properties"), e.position++;
	let n = e.position;
	for (; e.input.charCodeAt(e.position) !== 0 && !N(e.input.charCodeAt(e.position)) && !F(e.input.charCodeAt(e.position));) e.position++;
	return e.position === n && A(e, "name of an alias node must contain at least one character"), En(e, n, e.position), !0;
}
function Rn(e, t) {
	I(e, !1), e.lineIndent < t && A(e, "deficient indentation");
}
function zn(e, t, n) {
	if (e.input.charCodeAt(e.position) !== 39) return !1;
	e.position++;
	let r = e.position, i = !0;
	for (; e.input.charCodeAt(e.position) !== 0;) {
		let a = e.input.charCodeAt(e.position);
		if (a === 39) {
			if (e.input.charCodeAt(e.position + 1) === 39) {
				i = !1, e.position += 2;
				continue;
			}
			let t = e.position;
			return e.position++, T(e, r, t, n.anchorStart, n.anchorEnd, n.tagStart, n.tagEnd, 2, 1, -1, i), !0;
		}
		j(a) ? (i = !1, Rn(e, t)) : e.position === e.lineStart && L(e) ? A(e, "unexpected end of the document within a single quoted scalar") : a !== 9 && a < 32 ? A(e, "expected valid JSON character") : e.position++;
	}
	A(e, "unexpected end of the stream within a single quoted scalar");
}
function Bn(e, t, n) {
	if (e.input.charCodeAt(e.position) !== 34) return !1;
	e.position++;
	let r = e.position, i = !0;
	for (; e.input.charCodeAt(e.position) !== 0;) {
		let a = e.input.charCodeAt(e.position);
		if (a === 34) {
			let t = e.position;
			return e.position++, T(e, r, t, n.anchorStart, n.anchorEnd, n.tagStart, n.tagEnd, 3, 1, -1, i), !0;
		}
		if (a === 92) {
			i = !1;
			let n = e.input.charCodeAt(++e.position);
			if (j(n)) Rn(e, t);
			else if (jn(n)) e.position++;
			else {
				let t = An(n);
				for (t === 0 && A(e, "unknown escape sequence"); t-- > 0;) e.position++, kn(e.input.charCodeAt(e.position)) < 0 && A(e, "expected hexadecimal character");
				e.position++;
			}
		} else j(a) ? (i = !1, Rn(e, t)) : e.position === e.lineStart && L(e) ? A(e, "unexpected end of the document within a double quoted scalar") : a !== 9 && a < 32 ? A(e, "expected valid JSON character") : e.position++;
	}
	A(e, "unexpected end of the stream within a double quoted scalar");
}
function Vn(e, t, n) {
	let r = e.input.charCodeAt(e.position), i = 1, a = -1, o = !1;
	if (r !== 124 && r !== 62) return !1;
	let s = r === 124 ? 4 : 5;
	for (e.position++; e.input.charCodeAt(e.position) !== 0;) {
		let n = e.input.charCodeAt(e.position), r = On(n);
		if (n === 43 || n === 45) i !== 1 && A(e, "repeat of a chomping mode identifier"), i = n === 43 ? 3 : 2, e.position++;
		else if (r >= 0) r === 0 && A(e, "bad explicit indentation width of a block scalar; it cannot be less than one"), o && A(e, "repeat of an indentation width identifier"), a = t + r - 1, o = !0, e.position++;
		else break;
	}
	let c = !1;
	for (; M(e.input.charCodeAt(e.position));) c = !0, e.position++;
	c && e.input.charCodeAt(e.position) === 35 && Nn(e), j(e.input.charCodeAt(e.position)) ? Mn(e) : e.input.charCodeAt(e.position) !== 0 && A(e, "a line break is expected");
	let l = o ? a : -1, u = 0, d = e.position, f = e.position;
	for (; e.input.charCodeAt(e.position) !== 0;) {
		let n = e.position, r = 0;
		for (; e.input.charCodeAt(n + r) === 32;) r++;
		let i = e.input.charCodeAt(n + r);
		if (i === 0) {
			l >= 0 ? r > l && (f = n + r) : r > 0 && (f = n + r);
			break;
		}
		if (n === e.lineStart && L(e, n)) break;
		if (!o && l === -1 && j(i) && (u = Math.max(u, r)), !o && l === -1 && !j(i) && (i === 9 && r < t && (e.position = n + r, A(e, "tab characters must not be used in indentation")), r < u && (e.position = n + r, A(e, "bad indentation of a mapping entry"))), l === -1 && i !== 0 && !j(i) && r < t) {
			e.lineIndent = r, e.position = n + r;
			break;
		}
		!o && i !== 0 && !j(i) && l === -1 && (l = r);
		let a = l === -1 ? t + 1 : l;
		if (i !== 0 && !j(i) && r < a) {
			e.lineIndent = r, e.position = n + r;
			break;
		}
		Nn(e), f = e.position, j(e.input.charCodeAt(e.position)) && (Mn(e), f = e.position);
	}
	return Pn(e, d, f), T(e, d, f, n.anchorStart, n.anchorEnd, n.tagStart, n.tagEnd, s, i, l), !0;
}
function Hn(e, t) {
	let n = e.input.charCodeAt(e.position), r = t === w;
	if (n === 0 || N(n) || n === 35 || n === 38 || n === 42 || n === 33 || n === 124 || n === 62 || n === 39 || n === 34 || n === 37 || n === 64 || n === 96 || r && F(n)) return !1;
	if (n === 63 || n === 45) {
		let t = e.input.charCodeAt(e.position + 1);
		if (P(t) || r && F(t)) return !1;
	}
	return !0;
}
function Un(e, t, n, r) {
	if (!Hn(e, n)) return !1;
	let i = e.position, a = e.position, o = e.input.charCodeAt(e.position), s = n === w, c = !1;
	for (; o !== 0 && !(e.position === e.lineStart && L(e));) {
		if (o === 58) {
			let t = e.input.charCodeAt(e.position + 1);
			if (P(t) || s && F(t)) break;
		} else if (o === 35) {
			if (N(e.input.charCodeAt(e.position - 1))) break;
		} else if (s && F(o)) break;
		else if (j(o)) {
			let n = e.position, r = e.line, i = e.lineStart, a = e.lineIndent;
			if (I(e, !1), e.lineIndent >= t) {
				c = !0, o = e.input.charCodeAt(e.position);
				continue;
			}
			e.position = n, e.line = r, e.lineStart = i, e.lineIndent = a;
			break;
		}
		M(o) || (a = e.position + 1), o = e.input.charCodeAt(++e.position);
	}
	return a === i ? !1 : (Pn(e, i, a), T(e, i, a, r.anchorStart, r.anchorEnd, r.tagStart, r.tagEnd, 1, 1, -1, !c), !0);
}
function R(e, t) {
	let n = e.line;
	I(e, !0), (e.line > n && e.lineIndent < t || e.firstTabInLine !== -1 && e.lineIndent < t) && A(e, "deficient indentation");
}
function Wn(e, t, n) {
	let r = e.input.charCodeAt(e.position), i = r === 123, a = e.position, o = !0;
	if (r !== 91 && r !== 123) return !1;
	let s = i ? 125 : 93;
	for (i ? wn(e, a, n.anchorStart, n.anchorEnd, n.tagStart, n.tagEnd, 2) : Cn(e, a, n.anchorStart, n.anchorEnd, n.tagStart, n.tagEnd, 2), e.position++; e.input.charCodeAt(e.position) !== 0;) {
		R(e, t);
		let n = e.input.charCodeAt(e.position);
		if (n === s) return e.position++, E(e), !0;
		o ? n === 44 && A(e, "expected the node content, but found ','") : A(e, "missed comma between flow collection entries");
		let r = !1, a = !1;
		n === 63 && N(e.input.charCodeAt(e.position + 1)) && (r = a = !0, e.position += 1, R(e, t));
		let c = e.line, l = O(e), u = z(e, t, w, !1, !0);
		R(e, t), n = e.input.charCodeAt(e.position), (i || a || e.line === c) && n === 58 ? (r = !0, e.position++, R(e, t), i || Tn(e, l), u || D(e), z(e, t, w, !1, !0) || D(e), R(e, t), i || E(e)) : i && r ? (u || D(e), D(e)) : i ? D(e) : r && (Tn(e, l), u || D(e), D(e), E(e)), n = e.input.charCodeAt(e.position), n === 44 ? (o = !0, e.position++) : o = !1;
	}
	A(e, "unexpected end of the stream within a flow collection");
}
function Gn(e, t, n) {
	if (e.firstTabInLine !== -1 || e.input.charCodeAt(e.position) !== 45 || !P(e.input.charCodeAt(e.position + 1))) return !1;
	for (Cn(e, e.position, n.anchorStart, n.anchorEnd, n.tagStart, n.tagEnd, 1); e.input.charCodeAt(e.position) === 45 && P(e.input.charCodeAt(e.position + 1));) {
		e.firstTabInLine !== -1 && (e.position = e.firstTabInLine, A(e, "tab characters must not be used in indentation"));
		let n = e.line;
		e.position++;
		let r = I(e, !0) > 0;
		if (e.firstTabInLine !== -1 && e.input.charCodeAt(e.position) === 45 && P(e.input.charCodeAt(e.position + 1)) && A(e, "bad indentation of a sequence entry"), r && e.lineIndent <= t ? D(e) : z(e, t, dn, !1, !0), I(e, !0), e.lineIndent < t || e.position >= e.length) break;
		e.lineIndent > t && A(e, "bad indentation of a sequence entry"), e.line === n && e.input.charCodeAt(e.position) === 45 && P(e.input.charCodeAt(e.position + 1)) && A(e, "bad indentation of a sequence entry");
	}
	return E(e), !0;
}
function Kn(e, t, n, r) {
	let i = !1, a = !1, o = !1, s = !1;
	if (e.firstTabInLine !== -1) return !1;
	let c = e.input.charCodeAt(e.position);
	for (; c !== 0;) {
		!i && e.firstTabInLine !== -1 && (e.position = e.firstTabInLine, A(e, "tab characters must not be used in indentation"));
		let l = e.input.charCodeAt(e.position + 1), u = e.line;
		if ((c === 63 || c === 58) && P(l)) o || (wn(e, e.position, r.anchorStart, r.anchorEnd, r.tagStart, r.tagEnd, 1), o = !0), c === 63 ? (i && D(e), a = !0, i = !0) : i ? i = !1 : (D(e), a = !0, i = !1), e.position += 1, s = !0;
		else {
			i && (D(e), i = !1);
			let t = O(e);
			if (!z(e, n, un, !1, !0)) break;
			if (e.line === u) {
				for (c = e.input.charCodeAt(e.position); M(c);) c = e.input.charCodeAt(++e.position);
				if (c === 58) {
					if (c = e.input.charCodeAt(++e.position), P(c) || A(e, "a whitespace character is expected after the key-value separator within a block mapping"), !o) {
						for (k(e, t), wn(e, t.position, r.anchorStart, r.anchorEnd, r.tagStart, r.tagEnd, 1), o = !0, z(e, n, un, !1, !0), c = e.input.charCodeAt(e.position); M(c);) c = e.input.charCodeAt(++e.position);
						e.position++;
					}
					a = !0, i = !1, s = !1;
				} else if (a) A(e, "expected ':' after a mapping key");
				else return r.anchorStart !== C || r.tagStart !== C ? (k(e, t), !1) : !0;
			} else if (a) A(e, "can not read a block mapping entry; a multiline key may not be an implicit key");
			else return r.anchorStart !== C || r.tagStart !== C ? (k(e, t), !1) : !0;
		}
		if (z(e, t, fn, !0, s) && (s = !1), i || s && (D(e), s = !1), I(e, !0), c = e.input.charCodeAt(e.position), (e.line === u || e.lineIndent > t) && c !== 0) A(e, "bad indentation of a mapping entry");
		else if (e.lineIndent < t) break;
	}
	return a ? (i && D(e), o && E(e), !0) : !1;
}
function z(e, t, n, r, i, a = !0) {
	e.depth >= e.maxDepth && A(e, `nesting exceeded maxDepth (${e.maxDepth})`), e.depth++;
	let o = 1, s = !1, c = !1, l = null, u = Dn(), d = n === fn || n === dn, f = d, p = d;
	if (r && I(e, !0) && (s = !0, o = e.lineIndent > t ? 1 : e.lineIndent === t ? 0 : -1), e.position === e.lineStart && L(e)) return e.depth--, !1;
	if (o === 1) for (;;) {
		let r = e.input.charCodeAt(e.position), i = O(e);
		if (s && o !== 1 && (r === 33 || r === 38)) break;
		if (s && p && (u.tagStart !== C || u.anchorStart !== C) && (r === 33 || r === 38)) {
			var m;
			let n = O(e), r = t + 1;
			if (Kn(e, e.position - e.lineStart, r, u) && ((m = e.events[n.eventsLength]) == null ? void 0 : m.type) === 3) return e.depth--, !0;
			k(e, n);
		}
		if (s && (r === 33 && u.tagStart !== C || r === 38 && u.anchorStart !== C) || !Fn(e, u, n === w) && !In(e, u)) break;
		l === null && (l = i), I(e, !0) ? (s = !0, f = p, o = e.lineIndent > t ? 1 : e.lineIndent === t ? 0 : -1) : f = !1;
	}
	if (f && (f = s || i), o === 1 || n === fn) {
		let r = n === w || n === un ? t : t + 1, i = e.position - e.lineStart;
		if (o === 1) if (f && (Gn(e, i, u) || Kn(e, i, r, u)) || Wn(e, r, u)) c = !0;
		else {
			let t = e.input.charCodeAt(e.position);
			if (l !== null && a && p && !f && t !== 124 && t !== 62) {
				var h;
				let t = O(e), n = l.position - l.lineStart;
				k(e, l), Kn(e, n, r, Dn()) && ((h = e.events[t.eventsLength]) == null ? void 0 : h.type) === 3 ? c = !0 : k(e, t);
			}
			!c && (d && Vn(e, r, u) || zn(e, r, u) || Bn(e, r, u) || Ln(e, u) || Un(e, r, n, u)) && (c = !0);
		}
		else o === 0 && (c = f && Gn(e, i, u));
	}
	return d = d && !c, !c && (u.anchorStart !== C || u.tagStart !== C || d) && (T(e, C, C, u.anchorStart, u.anchorEnd, u.tagStart, u.tagEnd, 1), c = !0), e.depth--, c || u.anchorStart !== C || u.tagStart !== C;
}
function qn(e) {
	if (e.lineIndent > 0 || e.input.charCodeAt(e.position) !== 37) return !1;
	e.position++;
	let t = e.position;
	for (; e.input.charCodeAt(e.position) !== 0 && !N(e.input.charCodeAt(e.position));) e.position++;
	let n = e.input.slice(t, e.position), r = [];
	for (n.length === 0 && A(e, "directive name must not be less than one character in length"); e.input.charCodeAt(e.position) !== 0 && !j(e.input.charCodeAt(e.position));) {
		for (; M(e.input.charCodeAt(e.position));) e.position++;
		if (e.input.charCodeAt(e.position) === 35 || j(e.input.charCodeAt(e.position)) || e.input.charCodeAt(e.position) === 0) break;
		let t = e.position;
		for (; e.input.charCodeAt(e.position) !== 0 && !N(e.input.charCodeAt(e.position));) e.position++;
		r.push(e.input.slice(t, e.position));
	}
	if (j(e.input.charCodeAt(e.position)) && Mn(e), n === "YAML") {
		e.directives.some((e) => e.kind === "yaml") && A(e, "duplication of %YAML directive"), r.length !== 1 && A(e, "YAML directive accepts exactly one argument");
		let t = /^([0-9]+)\.([0-9]+)$/.exec(r[0]);
		t === null && A(e, "ill-formed argument of the YAML directive"), parseInt(t[1], 10) !== 1 && A(e, "unacceptable YAML version of the document"), e.directives.push({
			kind: "yaml",
			version: r[0]
		});
	} else if (n === "TAG") {
		r.length !== 2 && A(e, "TAG directive accepts exactly two arguments");
		let [t, n] = r;
		hn.test(t) || A(e, "ill-formed tag handle (first argument) of the TAG directive"), ln.call(e.tagHandlers, t) && A(e, `there is a previously declared suffix for "${t}" tag handle`), bn.test(n) || A(e, "ill-formed tag prefix (second argument) of the TAG directive"), e.tagHandlers[t] = n, e.directives.push({
			kind: "tag",
			handle: t,
			prefix: n
		});
	}
	return !0;
}
function Jn(e) {
	e.directives = [], e.tagHandlers = Object.create(null);
	let t = !1;
	for (I(e, !0); qn(e);) t = !0, I(e, !0);
	let n = !1, r = !1, i = !0;
	if (e.lineIndent === 0 && e.input.charCodeAt(e.position) === 45 && e.input.charCodeAt(e.position + 1) === 45 && e.input.charCodeAt(e.position + 2) === 45 && P(e.input.charCodeAt(e.position + 3))) {
		n = !0;
		let t = e.line;
		e.position += 3, I(e, !0), i = e.line > t;
	} else t && A(e, "directives end mark is expected");
	let a = e.events.length;
	if (!n && e.position === e.lineStart && e.input.charCodeAt(e.position) === 46 && L(e)) {
		e.position += 3, I(e, !0);
		return;
	}
	if (Sn(e, n, !1), z(e, e.lineIndent - 1, fn, !1, i, i) || D(e), I(e, !0), e.position === e.lineStart && L(e) && (r = e.input.charCodeAt(e.position) === 46, r)) {
		let t = e.line;
		e.position += 3, I(e, !0), e.line === t && e.position < e.length && A(e, "end of the stream or a document separator is expected");
	}
	let o = e.events[a];
	(o == null ? void 0 : o.type) === 1 && (o.explicitEnd = r), E(e), !r && e.position < e.length && !(e.position === e.lineStart && L(e)) && A(e, "end of the stream or a document separator is expected");
}
function Yn(e, t) {
	let n = e.length, r = y(y(y({}, xn), t), {}, {
		input: `${e}\0`,
		length: n,
		position: 0,
		line: 0,
		lineStart: 0,
		lineIndent: 0,
		firstTabInLine: -1,
		depth: 0,
		directives: [],
		tagHandlers: Object.create(null),
		events: []
	}), i = e.indexOf("\0");
	for (i !== -1 && pt(e, i, "null byte is not allowed in input", r.filename), r.input.charCodeAt(r.position) === 65279 && r.position++; r.position < r.length && (I(r, !0), !(r.position >= r.length));) {
		let e = r.position;
		Jn(r), r.position === e && A(r, "can not read a document");
	}
	return r.events;
}
//#endregion
//#region src/load.ts
var Xn = y(y({}, xn), Jt);
function Zn(e, t = {}) {
	let n = y(y({}, Xn), t), r = String(e), i = Object.keys(xn), a = Object.keys(Jt);
	return cn(Yn(r, We(n, i)), y(y({}, We(n, a)), {}, { source: r }));
}
function Qn(e, t, n) {
	let r = null;
	typeof t == "function" ? r = t : typeof t == "object" && t && (n = t);
	let i = Zn(e, n);
	if (r === null) return i;
	for (let e of i) r(e);
}
function $n(e, t) {
	let n = Zn(e, t);
	if (n.length === 0) throw new b("expected a document, but the input is empty");
	if (n.length === 1) return n[0];
	throw new b("expected a single document in the stream, but found more");
}
//#endregion
//#region src/ast/nodes.ts
var B = class {
	constructor() {
		_(this, "tagged", !1), _(this, "flow", !1), _(this, "singleQuoted", !1), _(this, "doubleQuoted", !1), _(this, "literal", !1), _(this, "folded", !1);
	}
}, V = Symbol("INVALID");
function er(e) {
	let t = new Set([
		e.defaultScalarTag,
		e.defaultSequenceTag,
		e.defaultMappingTag
	].filter((e) => e !== void 0)), n = e.implicitScalarTags, r = e.tags.filter((e) => !(e.nodeKind === "scalar" && e.implicit) && !t.has(e)), i = e.tags.filter((e) => t.has(e));
	return [
		...n.map((e) => ({
			tag: e,
			implicitTag: !0
		})),
		...r.map((e) => ({
			tag: e,
			implicitTag: !1
		})),
		...i.map((e) => ({
			tag: e,
			implicitTag: !0
		}))
	];
}
function tr(e, t) {
	for (let n = 0, r = e.representTypes.length; n < r; n += 1) {
		let { tag: r, implicitTag: i } = e.representTypes[n];
		if (r.identify && r.identify(t)) {
			let e;
			return e = r.matchByTagPrefix && r.representTagName ? r.representTagName(t) : r.tagName, {
				tag: r,
				tagName: e,
				implicitTag: i
			};
		}
	}
	return null;
}
function H(e, t) {
	if (!e.noRefs && typeof t == "object" && t) {
		let n = e.refs.get(t);
		if (n) return n.anchor === void 0 && (n.anchor = `ref_${e.refCounter++}`), {
			kind: "alias",
			tag: "",
			style: new B(),
			anchor: n.anchor
		};
	}
	let n = tr(e, t);
	if (!n) {
		if (t === void 0 || e.skipInvalid) return V;
		throw new b(`unacceptable kind of an object to dump ${Object.prototype.toString.call(t)}`);
	}
	let { tag: r, tagName: i, implicitTag: a } = n, o = a ? i : qt(i);
	if (r.nodeKind === "scalar") {
		let e = new B();
		return e.tagged = !a, {
			kind: "scalar",
			tag: o,
			style: e,
			value: r.represent(t)
		};
	}
	if (r.nodeKind === "sequence") {
		let n = r.represent(t), i = new B();
		i.tagged = !a;
		let s = {
			kind: "sequence",
			tag: o,
			style: i,
			items: []
		};
		e.noRefs || e.refs.set(t, s);
		for (let t = 0, r = n.length; t < r; t += 1) {
			let r = H(e, n[t]);
			r === V && n[t] === void 0 && (r = H(e, null)), r !== V && s.items.push(r);
		}
		return s;
	}
	let s = r.represent(t), c = new B();
	c.tagged = !a;
	let l = {
		kind: "mapping",
		tag: o,
		style: c,
		items: []
	};
	e.noRefs || e.refs.set(t, l);
	for (let [t, n] of s) {
		let r = H(e, t);
		if (r === V) continue;
		let i = H(e, n);
		i !== V && l.items.push({
			key: r,
			value: i
		});
	}
	return l;
}
function nr(e, t, n = {}) {
	var r, i;
	let a = H({
		representTypes: er(t),
		noRefs: (r = n.noRefs) == null ? !1 : r,
		skipInvalid: (i = n.skipInvalid) == null ? !1 : i,
		refs: /* @__PURE__ */ new Map(),
		refCounter: 0
	}, e);
	return [{
		contents: a === V ? null : a,
		directives: []
	}];
}
//#endregion
//#region src/ast/visit.ts
var rr = Symbol("visit:break"), ir = Symbol("visit:skip");
function ar(e, t, n) {
	let r = t(e, n);
	if (r === rr) return !0;
	if (r === ir) return !1;
	let i = n.depth + 1;
	switch (e.kind) {
		case "sequence":
			for (let n of e.items) if (ar(n, t, {
				depth: i,
				parent: e,
				isKey: !1
			})) return !0;
			break;
		case "mapping":
			for (let { key: n, value: r } of e.items) if (ar(n, t, {
				depth: i,
				parent: e,
				isKey: !0
			}) || ar(r, t, {
				depth: i,
				parent: e,
				isKey: !1
			})) return !0;
			break;
	}
	return !1;
}
function or(e, t) {
	for (let n of e) if (n.contents && ar(n.contents, t, {
		depth: 0,
		parent: null,
		isKey: !1
	})) return;
}
//#endregion
//#region src/ast/presenter.ts
var sr = 65279, cr = 9, U = 10, lr = 13, ur = 32, dr = 33, fr = 34, pr = 35, mr = 37, hr = 38, gr = 39, _r = 42, vr = 44, yr = 45, W = 58, br = 61, xr = 62, Sr = 63, Cr = 64, wr = 91, Tr = 93, Er = 96, Dr = 123, Or = 124, kr = 125, G = {};
G[0] = "\\0", G[7] = "\\a", G[8] = "\\b", G[9] = "\\t", G[10] = "\\n", G[11] = "\\v", G[12] = "\\f", G[13] = "\\r", G[27] = "\\e", G[34] = "\\\"", G[92] = "\\\\", G[133] = "\\N", G[160] = "\\_", G[8232] = "\\L", G[8233] = "\\P";
var Ar = {
	indent: 2,
	seqNoIndent: !1,
	seqInlineFirst: !0,
	sortKeys: !1,
	lineWidth: 80,
	flowBracketPadding: !1,
	flowSkipCommaSpace: !1,
	flowSkipColonSpace: !1,
	quoteFlowKeys: !1,
	quoteStyle: "single",
	forceQuotes: !1,
	tagBeforeAnchor: !1
};
function jr(e) {
	return e.style.tagged ? e.tag : qt(e.tag);
}
function Mr(e) {
	let t = y(y({}, Ar), e);
	return y(y({}, t), {}, {
		defaultScalarTagName: t.schema.defaultScalarTag.tagName,
		implicitResolvers: t.schema.implicitScalarTags
	});
}
function Nr(e) {
	let t = e.toString(16).toUpperCase(), n = e <= 255 ? "x" : "u", r = e <= 255 ? 2 : 4;
	return `\\${n}${"0".repeat(r - t.length)}${t}`;
}
function Pr(e, t) {
	let n = " ".repeat(t), r = 0, i = "", a = e.length;
	for (; r < a;) {
		let t, o = e.indexOf("\n", r);
		o === -1 ? (t = e.slice(r), r = a) : (t = e.slice(r, o + 1), r = o + 1), t.length && t !== "\n" && (i += n), i += t;
	}
	return i;
}
function Fr(e, t) {
	return `\n${" ".repeat(e.indent * t)}`;
}
function Ir(e, t) {
	let n = e.indent * Math.max(1, t);
	return {
		indent: n,
		blockIndent: t === 0 ? e.indent + 1 : e.indent,
		lineWidth: e.lineWidth === -1 ? -1 : Math.max(Math.min(e.lineWidth, 40), e.lineWidth - n)
	};
}
function Lr(t, n) {
	for (let r = 0, i = t.implicitResolvers.length; r < i; r += 1) {
		let i = t.implicitResolvers[r];
		if (i.resolve(n, !1, i.tagName) !== e) return i.tagName;
	}
	return t.defaultScalarTagName;
}
function K(e) {
	return e === ur || e === cr;
}
function Rr(e) {
	let t = e.charCodeAt(0);
	if (t !== yr && t !== 46 || e.charCodeAt(1) !== t || e.charCodeAt(2) !== t) return !1;
	if (e.length === 3) return !0;
	let n = e.charCodeAt(3);
	return K(n) || n === lr || n === U;
}
function q(e) {
	return e >= 32 && e <= 126 || e >= 161 && e <= 55295 && e !== 8232 && e !== 8233 || e >= 57344 && e <= 65533 && e !== sr || e >= 65536 && e <= 1114111;
}
function zr(e) {
	return q(e) && e !== sr && e !== lr && e !== U;
}
function Br(e, t, n) {
	let r = zr(e), i = r && !K(e);
	return (n ? r : r && e !== vr && e !== wr && e !== Tr && e !== Dr && e !== kr) && e !== pr && !(t === W && !i) || zr(t) && !K(t) && e === pr || t === W && i && (n || e !== vr && e !== wr && e !== Tr && e !== Dr && e !== kr);
}
function Vr(e) {
	return q(e) && e !== sr && !K(e) && e !== yr && e !== Sr && e !== W && e !== vr && e !== wr && e !== Tr && e !== Dr && e !== kr && e !== pr && e !== hr && e !== _r && e !== dr && e !== Or && e !== br && e !== xr && e !== gr && e !== fr && e !== mr && e !== Cr && e !== Er;
}
function Hr(e, t) {
	let n = J(e, 0);
	if (Vr(n)) return !0;
	if (e.length > 1 && (n === yr || n === Sr || n === W)) {
		let r = J(e, 1);
		return !K(r) && Br(r, n, t);
	}
	return !1;
}
function Ur(e) {
	return !K(e) && e !== W;
}
function J(e, t) {
	let n = e.charCodeAt(t), r;
	return n >= 55296 && n <= 56319 && t + 1 < e.length && (r = e.charCodeAt(t + 1), r >= 56320 && r <= 57343) ? (n - 55296) * 1024 + r - 56320 + 65536 : n;
}
function Wr(e) {
	return /^\n* /.test(e);
}
var Y = 1, X = 2, Gr = 3, Kr = 4, Z = 5;
function qr(e, t, n, r, i, a) {
	let { blockIndent: o, lineWidth: s } = n, c, l = 0, u = -1, d = !1, f = !1, p = s !== -1, m = -1, h = !Rr(t) && Hr(t, a) && Ur(J(t, t.length - 1));
	if (r || i) for (c = 0; c < t.length; l >= 65536 ? c += 2 : c++) {
		if (l = J(t, c), !q(l)) return Z;
		h = h && Br(l, u, a), u = l;
	}
	else {
		for (c = 0; c < t.length; l >= 65536 ? c += 2 : c++) {
			if (l = J(t, c), l === U) d = !0, p && (f = f || c - m - 1 > s && t[m + 1] !== " ", m = c);
			else if (!q(l)) return Z;
			h = h && Br(l, u, a), u = l;
		}
		f = f || p && c - m - 1 > s && t[m + 1] !== " ";
	}
	return !d && !f ? h && !i ? Y : e.quoteStyle === "double" ? Z : X : o > 9 && Wr(t) ? Z : f ? Kr : Gr;
}
function Jr(e, t, n) {
	let { indent: r, blockIndent: i, lineWidth: a } = n;
	switch (t) {
		case Y: return Zr(e, r);
		case X: return `'${Zr(e, r).replace(/'/g, "''")}'`;
		case Gr: return "|" + Xr(e, i) + Qr(Pr(e, r));
		case Kr: return ">" + Xr(e, i) + Qr(Pr($r(e, a), r));
		case Z: return `"${ti(e)}"`;
	}
}
function Yr(e, t, n, r, i) {
	let a = r || !i;
	if (t.style.singleQuoted) return X;
	if (t.style.doubleQuoted) return Z;
	if (!a) {
		if (t.style.literal) return Gr;
		if (t.style.folded) return Kr;
	}
	let o = t.value;
	if (o.length === 0) return t.style.tagged || Lr(e, o) === t.tag ? Y : e.quoteStyle === "double" ? Z : X;
	let s = qr(e, o, n, a, e.forceQuotes && !r, i);
	return s === Y && !t.style.tagged && Lr(e, o) !== t.tag ? e.quoteStyle === "double" ? Z : X : s;
}
function Xr(e, t) {
	let n = Wr(e) ? String(t) : "", r = e[e.length - 1] === "\n";
	return `${n}${r && (e[e.length - 2] === "\n" || e === "\n") ? "+" : r ? "" : "-"}\n`;
}
function Zr(e, t) {
	let n = e.indexOf("\n");
	if (n === -1) return e;
	let r = " ".repeat(t), i = e.slice(0, n), a = /(\n+)([^\n]*)/g;
	a.lastIndex = n;
	let o;
	for (; o = a.exec(e);) {
		let e = o[1].length, t = o[2];
		i += "\n".repeat(e + 1) + r + t;
	}
	return i;
}
function Qr(e) {
	return e[e.length - 1] === "\n" ? e.slice(0, -1) : e;
}
function $r(e, t) {
	let n = /(\n+)([^\n]*)/g, r = e.indexOf("\n");
	r === -1 && (r = e.length), n.lastIndex = r;
	let i = ei(e.slice(0, r), t), a = e[0] === "\n" || e[0] === " ", o, s;
	for (; s = n.exec(e);) {
		let e = s[1], n = s[2];
		o = n[0] === " ", i += e + (!a && !o && n !== "" ? "\n" : "") + ei(n, t), a = o;
	}
	return i;
}
function ei(e, t) {
	if (e === "" || e[0] === " ") return e;
	let n = / [^ ]/g, r, i = 0, a, o = 0, s = 0, c = "";
	for (; r = n.exec(e);) s = r.index, s - i > t && (a = o > i ? o : s, c += `\n${e.slice(i, a)}`, i = a + 1), o = s;
	return c += "\n", e.length - i > t && o > i ? c += `${e.slice(i, o)}\n${e.slice(o + 1)}` : c += e.slice(i), c.slice(1);
}
function ti(e) {
	let t = "", n = 0;
	for (let r = 0; r < e.length; n >= 65536 ? r += 2 : r++) {
		n = J(e, r);
		let i = G[n];
		if (i) {
			t += i;
			continue;
		}
		if (q(n)) {
			t += e[r], n >= 65536 && (t += e[r + 1]);
			continue;
		}
		t += Nr(n);
	}
	return t;
}
function ni(e, t, n) {
	let r = "";
	for (let i = 0, a = n.items.length; i < a; i += 1) {
		let a = Q(e, t, n.items[i], {});
		r !== "" && (r += `,${e.flowSkipCommaSpace ? "" : " "}`), r += a;
	}
	let i = e.flowBracketPadding && r !== "" ? " " : "";
	return `[${i}${r}${i}]`;
}
function ri(e, t, n, r) {
	let i = "";
	for (let a = 0, o = n.items.length; a < o; a += 1) {
		let o = Q(e, t + 1, n.items[a], {
			block: !0,
			compact: e.seqInlineFirst,
			isblockseq: !0
		});
		(!r || i !== "") && (i += Fr(e, t)), o === "" || U === o.charCodeAt(0) ? i += "-" : i += "- ", i += o;
	}
	return i;
}
function ii(e, t, n) {
	let r = "", i = oi(e, n.items);
	for (let { key: n, value: a } of i) {
		let i = "";
		r !== "" && (i += `,${e.flowSkipCommaSpace ? "" : " "}`);
		let o = Q(e, t, n, { iskey: !0 }), s = o.length > 1024;
		s ? i += "? " : e.quoteFlowKeys && (i += "\"");
		let c = Q(e, t, a, {}), l = e.flowSkipColonSpace || c === "" ? "" : " ";
		i += `${o}${e.quoteFlowKeys && !s ? "\"" : ""}:${l}${c}`, r += i;
	}
	let a = e.flowBracketPadding && r !== "" ? " " : "";
	return `{${a}${r}${a}}`;
}
function ai(e) {
	return e.kind === "scalar" ? e.value : e;
}
function oi(e, t) {
	if (!e.sortKeys) return t;
	let n = t.slice();
	if (e.sortKeys === !0) n.sort((e, t) => {
		let n = ai(e.key), r = ai(t.key);
		return n < r ? -1 : +(n > r);
	});
	else {
		let t = e.sortKeys;
		n.sort((e, n) => t(ai(e.key), ai(n.key)));
	}
	return n;
}
function si(e, t, n, r) {
	let i = "", a = oi(e, n.items);
	for (let n = 0, o = a.length; n < o; n += 1) {
		let o = "";
		(!r || i !== "") && (o += Fr(e, t));
		let { key: s, value: c } = a[n], l = (s.kind === "mapping" || s.kind === "sequence") && !s.style.flow && s.items.length !== 0 || s.kind === "scalar" && (s.style.literal || s.style.folded), u = l ? Q(e, t + 1, s, {
			block: !0,
			compact: !0,
			isblockseq: !ci(e, s, t + 1)
		}) : Q(e, t + 1, s, {
			block: !0,
			compact: !0,
			iskey: !0
		}), d = s.kind === "scalar" && s.value.indexOf("\n") !== -1, f = l || d || u.length > 1024;
		f && (u && U === u.charCodeAt(0) ? o += "?" : o += "? "), o += u, f && (o += Fr(e, t));
		let p = Q(e, t + 1, c, {
			block: !0,
			compact: f,
			isblockseq: f && !ci(e, c, t + 1)
		}), m = s.kind === "scalar" && s.value === "" && u !== "" && u.charCodeAt(u.length - 1) !== gr && u.charCodeAt(u.length - 1) !== fr, h = !f && (s.kind === "alias" || m) ? " " : "";
		p === "" || U === p.charCodeAt(0) ? o += `${h}:` : o += `${h}: `, o += p, i += o;
	}
	return i;
}
function ci(e, t, n) {
	return t.style.tagged || t.anchor !== void 0 || e.indent < 2 && n > 0;
}
function Q(e, t, n, r) {
	var i;
	if (n.kind === "alias") return `*${n.anchor}`;
	let { block: a = !1, iskey: o = !1, isblockseq: s = !1 } = r, c = (i = r.compact) == null ? !1 : i, l = n.anchor !== void 0;
	ci(e, n, t) && (c = !1);
	let u, d = n.style.tagged, f = a && (n.kind === "mapping" || n.kind === "sequence") && !n.style.flow && n.items.length !== 0;
	if (n.kind === "mapping") u = f ? si(e, t, n, c) : ii(e, t, n);
	else if (n.kind === "sequence") u = f ? e.seqNoIndent && !s && t > 0 ? ri(e, t - 1, n, c) : ri(e, t, n, c) : ni(e, t, n);
	else {
		let r = Ir(e, t), i = Yr(e, n, r, o, a);
		u = Jr(n.value, i, r), d = n.style.tagged || i !== Y && n.tag !== e.defaultScalarTagName;
	}
	if (f && c && t > 0 && e.indent > 2 && (u = `${" ".repeat(e.indent - 2)}${u}`), d || l) {
		let t = [], r = d ? jr(n) : null, i = l ? `&${n.anchor}` : null;
		e.tagBeforeAnchor ? (r !== null && t.push(r), i !== null && t.push(i)) : (i !== null && t.push(i), r !== null && t.push(r));
		let a = u === "" || u.charCodeAt(0) === U ? "" : " ";
		u = `${t.join(" ")}${a}${u}`;
	}
	return u;
}
function li(e) {
	return (e.kind === "sequence" || e.kind === "mapping") && !e.style.flow && e.items.length !== 0 && !e.style.tagged && e.anchor === void 0;
}
function ui(e) {
	let t = e;
	for (; (t.kind === "sequence" || t.kind === "mapping") && !t.style.flow && t.items.length !== 0;) t = t.kind === "sequence" ? t.items[t.items.length - 1] : t.items[t.items.length - 1].value;
	if (t.kind !== "scalar" || !(t.style.literal || t.style.folded)) return !1;
	let { value: n } = t;
	return n.endsWith("\n\n") || n === "\n";
}
function di(e) {
	let t = "";
	for (let n of e.directives) {
		if (n.kind === "yaml") {
			t += `%YAML ${n.version}\n`;
			continue;
		}
		let { handle: e, prefix: r } = n;
		t += `%TAG ${e} ${r}\n`;
	}
	return t;
}
function fi(e, t) {
	let n = Mr(t), r = "", i = !1;
	for (let t = 0; t < e.length; t += 1) {
		let a = e[t], o = di(a), s = o !== "", c = a.explicitStart || s || t > 0 && !i;
		if (r += o, a.contents === null) c && (r += "---\n");
		else if (c) {
			let e = Q(n, 0, a.contents, {
				block: !0,
				compact: !0
			}), t = e === "" ? "" : s || li(a.contents) ? "\n" : " ";
			r += `---${t}${e}\n`;
		} else r += Q(n, 0, a.contents, {
			block: !0,
			compact: !0
		}) + "\n";
		i = a.explicitEnd || a.contents !== null && ui(a.contents), i && (r += "...\n");
	}
	return r;
}
//#endregion
//#region src/dump.ts
var pi = rt.withTags(y(y({}, _e), {}, { resolve: (t, n, r) => {
	let i = _e.resolve(t, n, r);
	return i === e ? ce.resolve(t, n, r) : i;
} }), y(y({}, Me), {}, { resolve: (t, n, r) => {
	let i = Me.resolve(t, n, r);
	return i === e ? Se.resolve(t, n, r) : i;
} })), mi = y(y({}, Ar), {}, {
	schema: pi,
	skipInvalid: !1,
	noRefs: !1,
	flowLevel: -1,
	transform: () => {}
});
function hi(e, t = {}) {
	let n = y(y({}, mi), t), r = nr(e, n.schema, {
		noRefs: n.noRefs,
		skipInvalid: n.skipInvalid
	});
	return n.flowLevel >= 0 && or(r, (e, t) => {
		if (!(t.depth < n.flowLevel)) return e.style.flow = !0, ir;
	}), n.transform(r), fi(r, y(y({}, We(n, Object.keys(Ar))), {}, { schema: n.schema }));
}
//#endregion
//#region src/ast/from_events.ts
var $ = -1;
function gi(e) {
	return "tagStart" in e && e.tagStart !== $ ? e.tagStart : "anchorStart" in e && e.anchorStart !== $ ? e.anchorStart : "valueStart" in e && e.valueStart !== $ ? e.valueStart : "start" in e ? e.start : 0;
}
function _i(e, t) {
	return t.tagStart === $ ? "" : e.source.slice(t.tagStart, t.tagEnd);
}
function vi(e, t) {
	return t.anchorStart === $ ? void 0 : e.source.slice(t.anchorStart, t.anchorEnd);
}
function yi(t, n) {
	var r;
	let { schema: i } = t, a = (r = i.implicitScalarByFirstChar.get(n.charAt(0))) == null ? i.implicitScalarAnyFirstChar : r;
	for (let t of a) if (t.resolve(n, !1, t.tagName) !== e) return t.tagName;
	return i.defaultScalarTag.tagName;
}
function bi(e, t) {
	let n = Ut(e.source, t), r = _i(e, t), i = new B();
	switch (t.style) {
		case 2:
			i.singleQuoted = !0;
			break;
		case 3:
			i.doubleQuoted = !0;
			break;
		case 4:
			i.literal = !0;
			break;
		case 5:
			i.folded = !0;
			break;
	}
	let a;
	return r === "" ? a = t.style === 1 ? yi(e, n) : e.schema.defaultScalarTag.tagName : (i.tagged = !0, a = r), {
		kind: "scalar",
		tag: a,
		style: i,
		anchor: vi(e, t),
		value: n
	};
}
function xi(e, t, n) {
	let r = _i(e, t), i = new B();
	t.style === 2 && (i.flow = !0);
	let a;
	return r === "" ? a = n : (a = r, i.tagged = !0), {
		tag: a,
		style: i,
		anchor: vi(e, t)
	};
}
function Si(e, t) {
	let n = e.frames[e.frames.length - 1];
	n.kind === "document" ? n.doc.contents = t : n.kind === "sequence" ? n.node.items.push(t) : n.key ? (n.node.items.push({
		key: n.key,
		value: t
	}), n.key = null) : n.key = t;
}
function Ci(e, t) {
	let n = {
		source: t.source,
		schema: t.schema,
		eventIndex: 0,
		position: 0,
		frames: [],
		documents: []
	};
	for (; n.eventIndex < e.length;) {
		let t = e[n.eventIndex++];
		switch (n.position = gi(t), t.type) {
			case 1: {
				let e = {
					contents: null,
					explicitStart: t.explicitStart,
					explicitEnd: t.explicitEnd,
					directives: t.directives
				};
				n.frames.push({
					kind: "document",
					doc: e
				});
				break;
			}
			case 4:
				Si(n, bi(n, t));
				break;
			case 2: {
				let { tag: e, style: r, anchor: i } = xi(n, t, "tag:yaml.org,2002:seq"), a = {
					kind: "sequence",
					tag: e,
					style: r,
					anchor: i,
					items: []
				};
				n.frames.push({
					kind: "sequence",
					node: a
				});
				break;
			}
			case 3: {
				let { tag: e, style: r, anchor: i } = xi(n, t, "tag:yaml.org,2002:map"), a = {
					kind: "mapping",
					tag: e,
					style: r,
					anchor: i,
					items: []
				};
				n.frames.push({
					kind: "mapping",
					node: a,
					key: null
				});
				break;
			}
			case 5: {
				let e = n.source.slice(t.anchorStart, t.anchorEnd);
				Si(n, {
					kind: "alias",
					tag: "",
					style: new B(),
					anchor: e
				});
				break;
			}
			case 6: {
				let e = n.frames.pop();
				e.kind === "document" ? n.documents.push(e.doc) : Si(n, e.node);
				break;
			}
		}
	}
	return n.documents;
}
//#endregion
export { Dt as CHOMPING_CLIP, kt as CHOMPING_KEEP, Ot as CHOMPING_STRIP, Tt as COLLECTION_STYLE_BLOCK, Et as COLLECTION_STYLE_FLOW, nt as CORE_SCHEMA, vt as EVENT_ALIAS, mt as EVENT_DOCUMENT, gt as EVENT_MAPPING, yt as EVENT_POP, _t as EVENT_SCALAR, ht as EVENT_SEQUENCE, et as FAILSAFE_SCHEMA, tt as JSON_SCHEMA, t as MERGE_KEY, e as NOT_RESOLVED, St as SCALAR_STYLE_DOUBLE_QUOTED, wt as SCALAR_STYLE_FOLDED_BLOCK, Ct as SCALAR_STYLE_LITERAL_BLOCK, bt as SCALAR_STYLE_PLAIN, xt as SCALAR_STYLE_SINGLE_QUOTED, v as Schema, B as Style, rr as VISIT_BREAK, ir as VISIT_SKIP, rt as YAML11_SCHEMA, b as YAMLException, Le as binaryTag, p as boolCoreTag, ee as boolJsonTag, re as boolYaml11Tag, cn as constructFromEvents, i as defineMappingTag, n as defineScalarTag, r as defineSequenceTag, hi as dump, Ci as eventsToAst, Se as floatCoreTag, De as floatJsonTag, Me as floatYaml11Tag, Ut as getScalarValue, ce as intCoreTag, pe as intJsonTag, _e as intYaml11Tag, nr as jsToAst, ot as legacyMapTag, $n as load, Qn as loadAll, qe as mapTag, Ne as mergeTag, s as nullCoreTag, c as nullJsonTag, u as nullYaml11Tag, Ge as omapTag, Ke as pairsTag, Yn as parseEvents, fi as present, it as realMapTag, He as seqTag, Je as setTag, a as strTag, Ve as timestampTag, or as visit };

//# sourceMappingURL=js-yaml.esm.min.mjs.map