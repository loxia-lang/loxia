---
title: Classes and inheritance
description: Constructors, fields, overriding and super.
---

A small animal hierarchy. Fields are declared in the class body; `init` constructs an
instance; a subclass can call `super.init` and override a method.

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
  init(name: String) {
    super.init(name)
  }

  speak() -> String {
    return this.name + " barks"
  }
}

val animals: List[Animal] = [Animal("generic"), Dog("Rex")]
for animal in animals {
  print(animal.speak())
}
```

`List[Animal]` accepts a `Dog` because class types are covariant for reading. The method
call dispatches on the runtime class; `super.speak()` would call the parent implementation.

## A value object

<!-- run -->
```lox
class Point {
  val x: Int
  val y: Int

  init(x: Int, y: Int) {
    this.x = x
    this.y = y
  }

  add(other: Point) -> Point {
    return Point(this.x + other.x, this.y + other.y)
  }

  show() -> String {
    return "(${this.x}, ${this.y})"
  }
}

print(Point(1, 2).add(Point(3, 4)).show())
```
