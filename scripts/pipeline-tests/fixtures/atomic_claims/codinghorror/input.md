# The Best Code is No Code At All

Rich Skrenta writes that [code is our enemy](https://web.archive.org/web/20070602152648/http://www.skrenta.com/2007/05/code_is_our_enemy.html).

Code is bad. It rots. It requires periodic maintenance. It has bugs that need to be found. New features mean old code has to be adapted. The more code you have, the more places there are for bugs to hide. The longer checkouts or compiles take. The longer it takes a new employee to make sense of your system. If you have to refactor there’s more stuff to move around.

Code is produced by engineers. To make more code requires more engineers. Engineers have n^2 communication costs, and all that code they add to the system, while expanding its capability, also increases a whole basket of costs. You should do whatever possible to increase the productivity of individual programmers in terms of the expressive power of the code they write. Less code to do the same thing (and possibly better). Less programmers to hire. Less organizational communication costs.

Rich hints at it here, but the real problem isn’t the code. The code, like a newborn babe, is blameless and innocent the minute it is written into the world. Code isn’t our enemy. You want to see the real enemy? [Go look in the mirror](https://blog.codinghorror.com/on-the-meaning-of-coding-horror/). There’s your problem, right there.

**As a software developer, you are your own worst enemy. The sooner you realize that, the better off you’ll be.**

I know you have the best of intentions. We all do. We’re software developers; we love writing code. It’s what we do. We never met a problem we couldn’t solve with some duct tape, a jury-rigged coat hanger, and a pinch of code. But Wil Shipley argues that we should [rein in our natural tendencies](https://web.archive.org/web/20070601154320/http://wilshipley.com/blog/2007/05/pimp-my-code-part-14-be-inflexible.html) to write lots of code:

The fundamental nature of coding is that our task, as programmers, is to recognize that every decision we make is a trade-off. To be a master programmer is to understand the nature of these trade-offs, and be conscious of them in everything we write.

In coding, you have many dimensions in which you can rate code:

- Brevity of code
- Featurefulness
- Speed of execution
- Time spent coding
- Robustness
- Flexibility
Now, remember, these dimensions are all in opposition to one another. You can spend three days writing a routine which is really beautiful and fast, so you’ve gotten two of your dimensions up, but you’ve spent three days, so the “time spent coding” dimension is way down.

So, when is this worth it? How do we make these decisions? The answer turns out to be very sane, very simple, and also the one nobody, ever, listens to:

Start with brevity. Increase the other dimensions as required by testing.

I couldn’t agree more. I’ve given similar advice when I [exhorted developers to Code Smaller](https://blog.codinghorror.com/code-smaller/). And I’m not talking about a [reductio ad absurdum](http://en.wikipedia.org/wiki/Reductio_ad_absurdum) contest where we use up all the clever tricks in our books to make the code fit into less physical space. **I’m talking about practical, sensible strategies to reduce the volume of code an individual programmer has to read to understand how a program works.** Here’s a trivial little example of what I’m talking about:

if (s == String.Empty) if (s == "")

It seems obvious to me that the latter case is better because it’s just plain *smaller*. And yet I’m virtually guaranteed to encounter developers who will fight me, almost [literally to the death](https://blog.codinghorror.com/are-you-there-god-its-me-microsoft/), because they’re absolutely convinced that the verbosity of `String.Empty`

is somehow friendlier to the compiler. As if I care about that. As if *anyone* cared about that!

It’s painful for most software developers to acknowledge this, because they love code so much, but **the best code is no code at all**. Every new line of code you willingly bring into the world is code that has to be debugged, code that has to be read and understood, code that has to be supported. Every time you write new code, you should do so reluctantly, under duress, because you completely exhausted all your other options. Code is only our enemy because there are so many of us programmers writing so damn much of it. If you *can’t* get away with no code, the next best thing is to **start with brevity**.

If you love writing code – really, truly *love to write code* – you’ll love it enough to write as little of it as possible.