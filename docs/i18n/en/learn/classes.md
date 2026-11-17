---
title: Classes, enums and match
description: Objects, inheritance, enums and exhaustive matching.
---

## Classes

Fields are declared in the class body. `init` constructs an instance; methods bind `this`
implicitly.

<!-- run -->
```lox
class Animal {
  val name: String

  init(name: String) {
    this.name = name
  }

  speak() -> String {
    return this.name + " makes a sound"
  }
}

class Dog(Animal) {
  speak() -> String {
    return this.name + " barks"
  }
}

val rex = Dog("Rex")
print(rex.speak())
print(rex.name)
```

A subclass inherits `init` when it does not define one. Use `super.init(...)` and
`super.method()` to call the parent explicitly. There is no `override` keyword;
overriding is silent, and the checker verifies signature compatibility.

## Enums

An enum is either a set of constants or a tagged union with payloads. Variants are
namespaced.

<!-- run -->
```lox
enum Shape {
  Circle(Float),
  Rect(Float, Float)
}

fn area(shape: Shape) -> Float {
  return match shape {
    Shape.Circle(r) => 3.14159 * r * r
    Shape.Rect(w, h) => w * h
  }
}

print(area(Shape.Circle(2.0)))
print(area(Shape.Rect(2.0, 3.0)))
```

`match` is an expression and must be exhaustive. Enum equality is structural.

Next: [errors and modules](errors-modules/).
